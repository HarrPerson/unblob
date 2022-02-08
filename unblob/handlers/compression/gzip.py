"""
Handler for gzip compression format based on standard documented
at https://datatracker.ietf.org/doc/html/rfc1952.

The handler will create valid chunks for each gzip compressed stream instead of
concatenating sequential streams into an overall ValidChunk.

We monkey patched Python builtin gzip's _GzipReader read() function to stop
reading as soon as it reach the EOF marker of the current gzip stream. This
is a requirement for unblob given that streams can be malformed and followed
by garbage/random content that triggers BadGzipFile errors when gzip
library tries to read the next stream header.
"""
import gzip
import io
import zlib
from typing import List, Optional

from structlog import get_logger

from ...file_utils import InvalidInputFormat, read_until_past
from ...models import Handler, ValidChunk
from ._gzip_reader import SingleMemberGzipReader

logger = get_logger()

GZIP2_CRC_LEN = 4
GZIP2_SIZE_LEN = 4
GZIP2_FOOTER_LEN = GZIP2_CRC_LEN + GZIP2_SIZE_LEN


class GZIPHandler(Handler):
    NAME = "gzip"

    YARA_RULE = r"""
    strings:
        // id1 & id2
        // compression method (0x8 = DEFLATE)
        // flags, 00011111 (0x1f) is the highest since the first 3 bits are reserved
        // unix time
        // eXtra FLags (2 or 4 per RFC1952 2.3.1)
        // Operating System (0-13, or 255 per RFC1952 2.3.1)
        $gzip_magic = { 1F 8B 08 (00 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 0A | 0B | 0C | 0D | 0E | 0F | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 1A | 1B | 1C | 1D | 1E) [4] (02 | 04) (00 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 0A | 0B | 0C | 0D | FF) }
    condition:
        $gzip_magic
    """

    def calculate_chunk(
        self, file: io.BufferedIOBase, start_offset: int
    ) -> Optional[ValidChunk]:

        fp = SingleMemberGzipReader(file)
        if not fp.read_header():
            return

        try:
            fp.read_until_eof()
        except (gzip.BadGzipFile, zlib.error) as e:
            raise InvalidInputFormat from e

        file.seek(GZIP2_FOOTER_LEN - len(fp.unused_data), io.SEEK_CUR)

        # Gzip files can be padded with zeroes
        end_offset = read_until_past(file, b"\x00")

        return ValidChunk(
            start_offset=start_offset,
            end_offset=end_offset,
        )

    @staticmethod
    def make_extract_command(inpath: str, outdir: str) -> List[str]:
        return ["7z", "x", "-y", inpath, f"-o{outdir}"]
