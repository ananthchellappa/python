#!/usr/bin/env python3

import argparse
import os

import webvtt


def chunked(vtt, chunk_size_mins):
    chunked_vtt = webvtt.WebVTT()
    chunk_size_secs = chunk_size_mins * 60

    chunk_start_in_seconds = None
    chunk_start = None
    maybe_chunk_end = None
    chunk_text = None

    for caption in vtt.captions:
        if chunk_start_in_seconds is None:
            chunk_start_in_seconds = caption.start_in_seconds
            chunk_start = caption.start
            chunk_text = ""

        chunk_text += caption.text + os.linesep
        maybe_chunk_end = caption.end

        if caption.end_in_seconds - chunk_start_in_seconds >= chunk_size_secs:
            # We have a new chunk with at least chunk_size_mins long
            chunked_vtt.captions.append(
                webvtt.Caption(
                    start=chunk_start,
                    end=maybe_chunk_end,
                    text=chunk_text,
                )
            )
            chunk_start_in_seconds = None
            chunk_start = None
            chunk_text = None
    else:
        # Last chunk needs to be included anyway
        if chunk_text:
            chunked_vtt.captions.append(
                webvtt.Caption(
                    start=chunk_start,
                    end=maybe_chunk_end,
                    text=chunk_text,
                )
            )

    return chunked_vtt


def main():
    parser = argparse.ArgumentParser(description="VTT file chunker")
    parser.add_argument(
        "file",
        help="VTT file",
    )
    parser.add_argument(
        "chunk_size",
        help="Chunk size in minutes",
        type=float,
    )
    args = parser.parse_args()
    print(
        f"Chunking {args.file} with at least {args.chunk_size} mins per chunk."
    )
    vtt = webvtt.read(args.file)
    chunked_vtt = chunked(vtt, args.chunk_size)

    output_file = f"{args.file}_chunked_{args.chunk_size}"
    print(f"Writing output file at {output_file}.vtt")
    chunked_vtt.save(output_file)


if __name__ == "__main__":
    main()
