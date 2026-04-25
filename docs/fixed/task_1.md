# Task 1: Navigation Cleanup and Redirection

## Problem Statement
The current navigation system contains several outdated or irrelevant links for the target user base. Specifically, the "Experiment Lab" (experiments), "PHM Portal" (external link), and "Utilities" links need to be removed to simplify the interface. A new link to the main PHM Accountants website must be established as the primary external reference.

## Context Discovery
- Navigation elements are primarily defined in `templates/base.html` within the sidebar component.
- The Dashboard (`templates/index.html`) also contains shortcut links to the Experiment Lab that need removal.
- `base.html` lines 106-118 contain the specific links: `/experiments`, `utilities.phm-accountants.co.uk`, and `portal.phm-accountants.co.uk`.
- `index.html` lines 18 and 107 contain links to `experiments_home`.
- Titles like "PHM Portal" in browser tabs will be preserved for branding consistency, but external navigation links will be removed/replaced.

## Resolution
1. **Sidebar (`base.html`):**
    - Removed the "Experiment Lab" and "Utilities" navigation links.
    - Updated the primary external button to point to `https://phm-accountants.co.uk/` with the label "PHM Website".
2. **Dashboard (`index.html`):**
    - Removed the "Experiment Lab" action button from the page header.
    - Removed the "Experiment Workspace" shortcut card from the "Operational Tools" section.

**Status:** Fixed
