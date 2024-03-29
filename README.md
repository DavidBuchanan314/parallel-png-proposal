# Parallel PNG Proposal

This is a proof-of-concept implementation of a parallel-decodable PNG format, based on ideas from https://github.com/brion/mtpng

It is fully backwards-compatible with existing PNG decoders.

However, it adds a new ancilliarry chunk, called `pLLD`, which advises compatible encoders that they may
decode the file in parallel pieces.

This specific implementation isn't particularly fast (It's written in Python), but it demonstrates how the data
can be split into independently decodable pieces. Another limitation of this implementation is that it does not support filters.

See `samples/parallel_out.png` for an example PNG, containing a `pLLD` chunk, and 8 `IDAT` chunks, each containing their own piece of the image.

## The `pLLD` Chunk

Short for "Parallel Decodable".

It must appear before the first `IDAT` chunk.

This chunk has only two fields:

| Piece height | 4 bytes |
|--------------|---------|
| Flags        | 1 byte  |

Piece height gives the height of each piece, in pixels. In instances where the image height is not evenly divisible by the piece height,
the last piece may be smaller (but not larger).

A decoder should be able to determine the number of such pieces by calculating `ceiling(image_height / piece_height)`. Each piece is stored in its own IDAT chunk.

If bit 0 of Flags is set, it indicates that the image is parallel-defilterable. This means that the filter type for the first row of each piece must never refer to the row above.

Flag bits 1-7 are reserved.