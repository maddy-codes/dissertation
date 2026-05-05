# Task 26: Fix LaTeX Root File Detection

## Problem
The LaTeX Workshop extension in VS Code is unable to find the root file for the dissertation, resulting in the error: `[Build] Cannot find LaTeX root file.` This prevents the user from building the dissertation PDF.

## Context
- The root LaTeX file is `dissertation_material/22830110_dissertation.tex`.
- The project structure includes chapters in `dissertation_material/chapters/`.
- LaTeX Workshop often fails to detect the root file when it's in a subdirectory or when building from an included chapter file.

## Proposed Plan
1. Add `% !TEX root = 22830110_dissertation.tex` to the top of `dissertation_material/22830110_dissertation.tex`.
2. Add `% !TEX root = ../22830110_dissertation.tex` to the top of all included chapter files in `dissertation_material/chapters/`.
3. (Optional) Configure `latex-workshop.latex.rootFile.indicator` or `latex-workshop.latex.rootFile.doNotPrompt` in `.vscode/settings.json` if needed, but magic comments are usually more portable.

## Implementation Details
- Target files: 
    - `dissertation_material/22830110_dissertation.tex`
    - `dissertation_material/chapters/*.tex`
