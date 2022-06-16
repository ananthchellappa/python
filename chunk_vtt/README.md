# chunk_vtt

# Install

pip install .

# Usage

```
$ chunk-vtt --help

usage: chunk-vtt [-h] file chunk_size

VTT file chunker

positional arguments:
  file        VTT file
  chunk_size  Chunk size in minutes

options:
  -h, --help  show this help message and exit
```

```
$ chunk-vtt sample/upwkt.vtt 0.2
Chunking sample/upwkt.vtt with at least 0.2 mins per chunk.
Writing output file at sample/upwkt.vtt_chunked_0.2.vtt
```
