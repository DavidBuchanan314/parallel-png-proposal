from os import read
from PIL import Image
import concurrent.futures
import zlib
from math import ceil
import argparse
import struct

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def read_png_chunk(stream):
	chunk_len = int.from_bytes(stream.read(4), "big")
	chunk_type = stream.read(4)
	body = stream.read(chunk_len)
	crc = int.from_bytes(stream.read(4), "big")
	assert(crc == zlib.crc32(body, zlib.crc32(chunk_type)))
	return chunk_type, body


def decode_image_piece(piece_data, is_first, is_last, width):
	if is_first:
		piece_data = piece_data[2:] # chop off zlib header
	if is_last:
		piece_data = piece_data[:-4] # chop off adler32
	
	d = zlib.decompressobj(wbits=-15)

	decompressed = d.decompress(piece_data)
	decompressed += d.flush()

	defiltered = b""
	stride = 1 + width * 3
	for i in range(0, len(decompressed), stride):
		assert(decompressed[i] == 0) # filter type none is all we currently support
		defiltered += decompressed[i+1:i+stride]

	return defiltered


def main(args):
	file_in = open(args.input, "rb")

	magic = file_in.read(len(PNG_MAGIC))
	assert(magic == PNG_MAGIC)

	chunk_type, ihdr = read_png_chunk(file_in)
	assert(chunk_type == b"IHDR")
	
	width, height, bitdepth, colourtype, compmeth, filtermeth, interlacemeth \
		= struct.unpack(">IIBBBBB", ihdr)#
	
	# these are just limitations of this particular implementation
	assert(bitdepth == 8)
	assert(colourtype == 2)
	assert(compmeth == 0)
	assert(filtermeth == 0)
	assert(interlacemeth == 0)

	print(f"[+] size={width}x{height}")

	while True:
		chunk_type, chunk_body = read_png_chunk(file_in)
		if chunk_type == b"pLLd":
			piece_height, flags = struct.unpack(">IB", chunk_body)
			pass
		elif chunk_type == b"IDAT":
			idat = chunk_body
			break
		else:
			print("[!] skipping over unrecognised chunk:", chunk_type)
	
	assert(flags == 1) # all we support, currently

	num_pieces = height // piece_height
	print(f"[+] Image is split into {num_pieces} pieces of height {piece_height}px")

	pieces = [idat]
	for _ in range(num_pieces - 1):
		chunk_type, idat = read_png_chunk(file_in)
		assert(chunk_type == b"IDAT")
		pieces.append(idat)
	
	chunk_type, iend_body = read_png_chunk(file_in)
	assert(chunk_type == b"IEND")

	print("[+] Finished parsing PNG chunks")

	pixels = b""
	with concurrent.futures.ThreadPoolExecutor() as executor:
		futures = []
		for i in range(len(pieces)):
			is_first = i == 0
			is_last = i == len(pieces) - 1
			futures.append(executor.submit(decode_image_piece, pieces[i], is_first, is_last, width))
		for future in futures:
			pixels += future.result()
	
	image = Image.frombytes("RGB", (width, height), pixels)
	image.save(args.output)
	print(f"[+] Saved to {args.output!r}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Decode a parallel-decodable PNG")
	parser.add_argument("input", help="Input file name")
	parser.add_argument("output", help="Output file name")
	args = parser.parse_args()
	main(args)