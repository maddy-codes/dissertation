import re
with open("app.py", "r") as f:
    content = f.read()

# Replace the whole analyze_scope route with our new analyze_scope_batch route
new_route = """@app.route("/api/workbench/analyze_scope_batch/<tenant_id>", methods=["POST"])
@login_required
def analyze_scope_batch(tenant_id):
    from helpers.batch_analyzer import analyze_nominal_batch
    tb_data = request.json.get("tb_data", [])
    global_mat = request.json.get("global_materiality", 1000)
    
    try:
        results = analyze_nominal_batch(tb_data, float(global_mat))
        return jsonify({"status": "Success", "data": {"coa_suggestions": results}})
    except Exception as e:
        return jsonify({"status": "Error", "message": str(e)}), 500
"""

# Regex to find the analyze_scope function and replace it
# Assuming it ends before the next @app.route
pattern = r'@app\.route\("/api/workbench/analyze_scope/<tenant_id>", methods=\["POST"\]\)\n@login_required\ndef analyze_scope\(tenant_id\):.*?return jsonify\({"status": "Error", "message": str\(e\)}\), 500'

if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_route, content, flags=re.DOTALL)
    with open("app.py", "w") as f:
        f.write(content)
    print("Replaced analyze_scope successfully")
else:
    print("Could not find analyze_scope")

