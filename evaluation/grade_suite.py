"""Compatibility wrapper: `--suite S --run R` is `evaluation.grade --references S --run R`."""
import sys

from evaluation.grade import grade, main  # noqa: F401  (grade kept for older imports)

if __name__ == '__main__':
    sys.exit(main(['--references' if a == '--suite' else a for a in sys.argv[1:]]))
