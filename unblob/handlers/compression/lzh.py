import io
from typing import List, Optional

from ...file_utils import Endian
from ...models import StructHandler, ValidChunk

PADDING_LEN = 2


class LZHHandler(StructHandler):

    NAME = "lzh"

    YARA_RULE = r"""
        strings:
            $lzh_magic_lh0 = "-lh0-"
            $lzh_magic_lzs = "-lzs-"
            $lzh_magic_lz4 = "-lz4-"
            $lzh_magic_lh1 = "-lh1-"
            $lzh_magic_lh2 = "-lh2-"
            $lzh_magic_lh3 = "-lh3-"
            $lzh_magic_lh4 = "-lh4-"
            $lzh_magic_lh5 = "-lh5-"
            $lzh_magic_lh6 = "-lh6-"
            $lzh_magic_lh7 = "-lh7-"
            $lzh_magic_lh8 = "-lh8-"
            $lzh_magic_lhd = "-lhd-"
        condition:
            any of them and
            // validate that level identifier is either 0x0, 0x1 or 0x2
            // the fact that we use 'or' is not problematic given that we check only one match at a time
            // so only one of those condition will be true
            (
                uint8(@lzh_magic_lh0 + 18) <= 0x02 or
                uint8(@lzh_magic_lzs + 18) <= 0x02 or
                uint8(@lzh_magic_lz4 + 18) <= 0x02 or
                uint8(@lzh_magic_lh1 + 18) <= 0x02 or
                uint8(@lzh_magic_lh2 + 18) <= 0x02 or
                uint8(@lzh_magic_lh3 + 18) <= 0x02 or
                uint8(@lzh_magic_lh4 + 18) <= 0x02 or
                uint8(@lzh_magic_lh5 + 18) <= 0x02 or
                uint8(@lzh_magic_lh6 + 18) <= 0x02 or
                uint8(@lzh_magic_lh7 + 18) <= 0x02 or
                uint8(@lzh_magic_lh8 + 18) <= 0x02 or
                uint8(@lzh_magic_lhd + 18) <= 0x02
            )
    """

    YARA_MATCH_OFFSET = -2

    C_DEFINITIONS = r"""
        typedef struct lzh_default_header {
            uint8 header_size;          // excludes extended headers size
            uint8 header_checksum;
            char method_id[5];
            uint32 compressed_size;     // includes all extended headers size (if level 1)
            uint32 uncompressed_size;
            uint32 timestamp;
            uint8 fd_attribute;
            uint8 level_identifier;
        } lzh_default_header_t;

        typedef struct level_2_header {
            uint16 header_size; // includes all extended headers
            char method_id[5];
            uint32 compressed_size;     // excludes all extended headers
            uint32 uncompressed_size;
            uint32 timestamp;
            uint8 fd_attribute;
            uint8 level_identifier;
        } level_2_header_t;
    """
    HEADER_STRUCT = "lzh_default_header_t"

    def calculate_chunk(
        self, file: io.BufferedIOBase, start_offset: int
    ) -> Optional[ValidChunk]:

        header = self.parse_header(file, Endian.LITTLE)

        if header.level_identifier == 0x2:
            # with level 2, the header size is a uint16 rather than uint8 and there
            # is no checksum. We use this magic trick so we don't parse the header
            # again. See the level_2_header definition in C_DEFINITIONS
            header_size = header.header_size + (header.header_checksum << 8)
        else:
            header_size = header.header_size + PADDING_LEN

        file.seek(-len(header), io.SEEK_CUR)
        file.seek(header_size + header.compressed_size, io.SEEK_CUR)
        end_offset = file.tell()

        # LZH files are null terminated, so we have to handle the case where
        # we matched the last LZH stream of a file and pad appropriately.
        file.seek(0, io.SEEK_END)
        end_pos = file.tell()

        if end_pos - end_offset == 1:
            end_offset = end_pos

        return ValidChunk(
            start_offset=start_offset,
            end_offset=end_offset,
        )

    @staticmethod
    def make_extract_command(inpath: str, outdir: str) -> List[str]:
        return ["7z", "x", "-y", inpath, f"-o{outdir}"]
