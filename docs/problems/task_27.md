# Task 27: Missing LaTeX Build Dependencies

## Problem
The build fails with `Error: spawn latexmk ENOENT`. This means the system is missing `latexmk` and likely the entire LaTeX distribution required to compile the dissertation.

## Context
- `which latexmk`, `which pdflatex`, etc. return empty.
- Common paths like `/Library/TeX/texbin` do not exist.
- Homebrew is available but doesn't have LaTeX formulae/casks installed (except `gettext`).
- Perl is available (required for `latexmk`).

## Proposed Plan
1. Inform the user that a LaTeX distribution is missing.
2. Suggest installing `BasicTeX` or `MacTeX`.
3. If the user wants an automated fix, try installing `BasicTeX` via Homebrew.
4. After installation, ensure the path is updated in VS Code or the system.

## Implementation Details
- Potential command: `brew install --cask basictex`
- Subsequent need: `sudo tlmgr update --self && sudo tlmgr install latexmk`
