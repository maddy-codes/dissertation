import re

with open("templates/workbench.html", "r") as f:
    content = f.read()

# 1. Remove btn-ai-recommend
content = re.sub(
    r'<button id="btn-ai-recommend" class="px-6 py-3.*?Run AI Intelligence Scan\s*</button>',
    '',
    content,
    flags=re.DOTALL
)

# 2. Update COA table header to include a column for the drill-down arrow
content = re.sub(
    r'<div class="grid grid-cols-\[auto_80px_1fr_100px_100px_200px\] gap-4 bg-surface-container-low px-8 py-4 border-b border-outline-variant text-\[10px\] font-black uppercase tracking-\[0\.2em\] text-primary">',
    '<div class="grid grid-cols-[auto_80px_1fr_100px_100px_200px_40px] gap-4 bg-surface-container-low px-8 py-4 border-b border-outline-variant text-[10px] font-black uppercase tracking-[0.2em] text-primary">',
    content
)
# Add an empty div for the header of the arrow column
content = re.sub(
    r'<div class="text-right">Recommendation</div>\s*</div>',
    '<div class="text-right">Recommendation</div><div></div></div>',
    content
)

# 3. Modify the initial COA row generation inside fetch_tb's `.then(data => {`
# We don't render them all at once now, or we render them but hide them? 
# The prompt says: "you load the tb line by line and in that line there should be a right arrow... batches of 5-10 nominals... async".
# So maybe we still render the rows empty, and then update them in batches, or we render them as we go.
# Let's replace the COA row generation inside JS.
js_replace_start = r'// COA Row.*?coaCont\.appendChild\(cel\);'
js_replace_end = r''
# Actually, replacing the whole JS block is easier.

# Instead of complex regex, let's just write a new block of JS and replace the whole <script> tag content.

