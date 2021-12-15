from PIL import Image
import concurrent.futures
import zlib
from math import ceil
import argparse

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
BASE = 65521

# https://github.com/madler/zlib/blob/cacf7f1d4e3d44d871b605da3b647f07d718623f/adler32.c#L143
def adler32_combine(adler1, adler2, len2):
	if adler1 is None:
		return adler2
	
	a1hi = adler1 >> 16
	a1lo = adler1 & 0xffff
	a2hi = adler2 >> 16
	a2lo = adler2 & 0xffff
	
	sum1 = (a1lo + a2lo - 1) % BASE
	sum2 = ((len2 * a1lo) + a1hi + a2hi - len2) % BASE
	
	return sum1 | (sum2 << 16)


def write_png_chunk(stream, name, body):
	stream.write(len(body).to_bytes(4, "big"))
	stream.write(name)
	stream.write(body)
	crc = zlib.crc32(body, zlib.crc32(name)) # zlib.crc32(name+body), but avoiding unnecessary data copies
	stream.write(crc.to_bytes(4, "big"))


def encode_image_piece(imgdata, width, height, ystart, yend):
	is_first = ystart == 0
	is_last = yend == height

	c = zlib.compressobj(level=9)
	idat = b""

	for y in range(ystart, yend):
		offset = 3*width*y
		idat += c.compress(b"\x00") # filter type none
		idat += c.compress(imgdata[offset:offset+3*width])
	
	if is_last:
		idat += c.flush(zlib.Z_FINISH)
		adler = int.from_bytes(idat[-4:], "big")
		idat = idat[:-4] # chop off the adler32
	else:
		idat += c.flush(zlib.Z_FULL_FLUSH)
		adler = int.from_bytes(c.flush(zlib.Z_FINISH)[-4:], "big") # throw in a Z_FINISH as a lazy way of grabbing the adler32
	
	if not is_first: # if this isn't the first piece, trim off the zlib header
		idat = idat[2:]
	
	piece_len = (width*3+1)*(yend-ystart)
	return idat, adler, piece_len


def main(args):
	img_in = Image.open(args.input).convert("RGB")
	outfile = open(args.output, "wb")
	width, height = img_in.size

	print(f"[+] Opened {args.input!r}, size={width}x{height}")

	piece_height = ceil(height / args.n) # NOTE: the last piece may be smaller, where n does not evenly divide height
	print(f"[+] Splitting into {args.n} pieces of height {piece_height}")

	outfile.write(PNG_MAGIC)

	ihdr = b""
	ihdr += width.to_bytes(4, "big")
	ihdr += height.to_bytes(4, "big")
	ihdr += (8).to_bytes(1, "big") # bitdepth
	ihdr += (2).to_bytes(1, "big") # truecolour
	ihdr += (0).to_bytes(1, "big") # compression method
	ihdr += (0).to_bytes(1, "big") # filter method
	ihdr += (0).to_bytes(1, "big") # interlace method


	write_png_chunk(outfile, b"IHDR", ihdr)

	plld = b""
	plld += piece_height.to_bytes(4, "big") # height of each piece
	plld += (1).to_bytes(1, "big") # parallel defilter supported

	assert(height // piece_height == args.n) # a decoder can quickly determine the number of pieces via floored division

	write_png_chunk(outfile, b"pLLd", plld) # pLLd stands for Parallel Decode

	raw_imgdata = img_in.tobytes()
	with concurrent.futures.ThreadPoolExecutor() as executor:
		futures = []

		for y in range(0, height, piece_height):
			futures.append(executor.submit(encode_image_piece, raw_imgdata, width, height, y, min(height, y + piece_height)))

		adler = None
		for i in range(args.n):
			body, chunk_adler, chunk_len = futures[i].result()
			adler = adler32_combine(adler, chunk_adler, chunk_len)

			if i == args.n - 1: # last chunk
				body += adler.to_bytes(4, "big") # append adler32

			write_png_chunk(outfile, b"IDAT", body)

	write_png_chunk(outfile, b"IEND", b"")
	outfile.close()


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Encode a parallel-decodable PNG")
	parser.add_argument("input", help="Input file name")
	parser.add_argument("output", help="Output file name")
	parser.add_argument('-n', type=int, default=8, help="The number of chunks to split the file into")
	args = parser.parse_args()
	main(args)