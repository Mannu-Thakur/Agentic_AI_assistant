import sys
import json
import math
import os
import ast

# Database file in the same folder
STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_store.json")

def load_root_store():
    if not os.path.exists(STORE_FILE):
        return {"users": {}}
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"users": {}}
            # Legacy format migration (if root file has top-level "expenses")
            if "expenses" in data or "reminders" in data:
                return {
                    "users": {
                        "default": {
                            "expenses": data.get("expenses", []),
                            "reminders": data.get("reminders", []),
                            "emails": data.get("emails", [])
                        }
                    }
                }
            if "users" not in data:
                data["users"] = {}
            return data
    except Exception as exc:
        sys.stderr.write(f"Failed to load mcp_store.json: {exc}\n")
        return None

def load_store(user_id: str = "default") -> dict:
    user_id = str(user_id or "default").strip()
    root = load_root_store()
    if root is None:
        root = {"users": {}}
    users = root.get("users", {})
    user_data = users.get(user_id)
    if not isinstance(user_data, dict):
        return {"expenses": [], "reminders": [], "emails": []}
    return {
        "expenses": list(user_data.get("expenses", [])),
        "reminders": list(user_data.get("reminders", [])),
        "emails": list(user_data.get("emails", []))
    }

def save_store(user_store: dict, user_id: str = "default"):
    user_id = str(user_id or "default").strip()
    root = load_root_store()
    if root is None:
        sys.stderr.write("Aborting save_store: failed to read root store safely\n")
        return
    root.setdefault("users", {})[user_id] = {
        "expenses": user_store.get("expenses", []),
        "reminders": user_store.get("reminders", []),
        "emails": user_store.get("emails", [])
    }
    tmp_file = f"{STORE_FILE}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(root, f, indent=2)
        os.replace(tmp_file, STORE_FILE)
    except Exception as exc:
        sys.stderr.write(f"Failed to save mcp_store.json: {exc}\n")
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


# Category aliases: map informal names to canonical categories
CATEGORY_ALIASES = {
    "fooding": "food",
    "foodings": "food",
    "food": "food",
    "fast food": "food",
    "fastfood": "food",
    "lunch": "food",
    "dinner": "food",
    "breakfast": "food",
    "bf": "food",
    "lun": "food",
    "dnnr": "food",
    "snack": "food",
    "snacks": "food",
    "meal": "food",
    "meals": "food",
    "coupon": "food",
    "groceries": "food",
    "grocery": "food",
    "eating": "food",
    "restaurant": "food",
    "restaurants": "food",
    "transport": "transport",
    "travel": "transport",
    "cab": "transport",
    "uber": "transport",
    "bills": "bills",
    "bill": "bills",
    "electricity": "bills",
    "rent": "bills",
    "shopping": "shopping",
    "clothing": "shopping",
    "entertainment": "entertainment",
    "movie": "entertainment",
    "health": "health",
    "medicine": "health",
    "medical": "health",
}

def normalize_category(category: str) -> str:
    """Normalize informal category names to canonical ones."""
    if not category:
        return "food"
    key = category.strip().lower()
    return CATEGORY_ALIASES.get(key, key)


SAFE_MATH_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "exp": math.exp, "sqrt": math.sqrt,
    "pi": math.pi, "e": math.e, "abs": abs, "round": round,
    "min": min, "max": max
}

def _eval_ast_node(node):
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)
    elif isinstance(node, (ast.Num, ast.Constant)):
        val = getattr(node, 'n', getattr(node, 'value', None))
        if type(val) in (int, float):
            return val
        raise ValueError("Only numeric constants allowed (booleans forbidden)")
    elif isinstance(node, ast.BinOp):
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        if isinstance(node.op, ast.Add): return left + right
        elif isinstance(node.op, ast.Sub): return left - right
        elif isinstance(node.op, ast.Mult): return left * right
        elif isinstance(node.op, ast.Div): return left / right
        elif isinstance(node.op, ast.FloorDiv): return left // right
        elif isinstance(node.op, ast.Mod): return left % right
        elif isinstance(node.op, ast.Pow):
            if abs(right) > 100 or abs(left) > 10000:
                raise ValueError("Exponentiation power limits exceeded (max base 10000, max exp 100)")
            return left ** right
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_ast_node(node.operand)
        if isinstance(node.op, ast.USub): return -operand
        elif isinstance(node.op, ast.UAdd): return +operand
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Attribute access or indirect function calls are strictly forbidden.")
        func_name = node.func.id
        if func_name not in SAFE_MATH_FUNCS:
            raise ValueError(f"Function '{func_name}' is not permitted.")
        args = [_eval_ast_node(arg) for arg in node.args]
        return SAFE_MATH_FUNCS[func_name](*args)
    elif isinstance(node, ast.Name):
        if node.id in SAFE_MATH_FUNCS:
            return SAFE_MATH_FUNCS[node.id]
        raise ValueError(f"Unknown variable or constant: '{node.id}'")
    raise ValueError(f"Operation or syntax '{type(node).__name__}' is forbidden in math expressions.")


def calculate(expression: str) -> str:
    """
    Safely evaluate basic mathematical expressions using AST parsing.
    """
    if not expression or not expression.strip():
        return "Error: Expression is empty."
    try:
        parsed = ast.parse(expression.strip(), mode="eval")
        val = _eval_ast_node(parsed)
        return str(val)
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"

def add_expense(amount: float, description: str, category: str = "food", date: str = None, currency: str = "₹", user_id: str = "default") -> str:
    store = load_store(user_id=user_id)
    canonical_cat = normalize_category(category)
    curr_sym = (currency or "₹").strip()
    expense = {
        "amount": amount,
        "description": description,
        "category": canonical_cat,
        "date": date or "",          # ISO date string e.g. "2026-07-02", or empty
        "currency": curr_sym,
    }
    store["expenses"].append(expense)
    save_store(store, user_id=user_id)
    date_str = f" on {date}" if date else ""
    return f"✅ Added expense: {curr_sym}{amount} for '{description}' (Category: {canonical_cat}{date_str})."

def get_expenses(category: str = None, date: str = None, user_id: str = "default") -> str:
    store = load_store(user_id=user_id)
    expenses = store["expenses"]

    # Category filter with alias normalization
    if category:
        cat_norm = normalize_category(category)
        expenses = [e for e in expenses if normalize_category(e.get("category", "")) == cat_norm]

    # Date filter (partial match: "2026-07-02" or "July 2026" etc.)
    if date:
        date_lower = date.strip().lower()
        expenses = [e for e in expenses if date_lower in e.get("date", "").lower()]

    if not expenses:
        filter_desc = []
        if category:
            filter_desc.append(f"category '{category}'")
        if date:
            filter_desc.append(f"date '{date}'")
        return f"No expenses found{' for ' + ' and '.join(filter_desc) if filter_desc else ''}."
    
    total = sum(float(e["amount"]) for e in expenses)
    first_curr = expenses[0].get("currency", "₹") if expenses else "₹"
    details = "\n".join(
        f"  • {e.get('currency', '₹')}{e['amount']} — {e['description']} [{e['category']}]"
        + (f" on {e['date']}" if e.get("date") else "")
        for e in expenses
    )
    filter_desc = []
    if category:
        filter_desc.append(f"category '{normalize_category(category)}'")
    if date:
        filter_desc.append(f"date '{date}'")
    header = f"Expenses{' (' + ', '.join(filter_desc) + ')' if filter_desc else ''}:"
    return f"{header}\n{details}\n\n💰 Total spent: {first_curr}{total:.2f}"

def summarize_expenses(user_id: str = "default") -> str:
    """Return a summary of all expenses grouped by category with per-category totals."""
    store = load_store(user_id=user_id)
    expenses = store["expenses"]
    if not expenses:
        return "No expenses tracked yet."

    # Group by category
    groups: dict = {}
    for e in expenses:
        cat = e.get("category", "uncategorized")
        groups.setdefault(cat, []).append(e)

    lines = []
    grand_total = 0.0
    first_curr = expenses[0].get("currency", "₹") if expenses else "₹"
    for cat, items in sorted(groups.items()):
        cat_total = sum(float(x["amount"]) for x in items)
        grand_total += cat_total
        cat_curr = items[0].get("currency", first_curr) if items else first_curr
        lines.append(f"\n📂 {cat.upper()} — {cat_curr}{cat_total:.2f}")
        for x in items:
            date_str = f" ({x['date']})" if x.get("date") else ""
            c_sym = x.get("currency", cat_curr)
            lines.append(f"    • {c_sym}{x['amount']} — {x['description']}{date_str}")

    return "📊 Expense Summary:\n" + "\n".join(lines) + f"\n\n💰 Grand Total: {first_curr}{grand_total:.2f}"

def create_reminder(time: str, text: str, user_id: str = "default") -> str:
    store = load_store(user_id=user_id)
    reminder = {
        "time": time,
        "text": text,
        "created_at": str(os.getenv("CURRENT_TIME", ""))
    }
    store["reminders"].append(reminder)
    save_store(store, user_id=user_id)
    return f"✅ Reminder set for {time}: '{text}'."

def get_reminders(user_id: str = "default") -> str:
    store = load_store(user_id=user_id)
    reminders = store.get("reminders", [])
    if not reminders:
        return "No reminders found."
    lines = [f"  • [{r.get('time', 'N/A')}] {r.get('text', '')}" for r in reminders]
    return "⏰ Active Reminders:\n" + "\n".join(lines)

def send_email(to: str, subject: str, body: str, user_id: str = "default") -> str:
    store = load_store(user_id=user_id)
    email_entry = {
        "to": to,
        "subject": subject,
        "body": body,
        "timestamp": str(os.getenv("CURRENT_TIME", ""))
    }
    store["emails"].append(email_entry)
    save_store(store, user_id=user_id)

    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if smtp_user and smtp_password:
        try:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["From"] = os.getenv("SMTP_FROM_EMAIL", smtp_user)
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)

            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10.0) as server:
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10.0) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            return f"📧 Real Email successfully dispatched via SMTP to {to} with subject '{subject}'."
        except Exception as exc:
            return f"❌ Email dispatch failed via SMTP: {exc} (Saved to local store for recovery)."

    return (
        f"❌ Email NOT sent — SMTP credentials (SMTP_USER/SMTP_PASSWORD) are not configured in environment. "
        f"The email to {to} was logged to local store (mcp_store.json) for debugging, but NO email was sent over the network. "
        f"Please configure SMTP settings in .env to enable live email delivery."
    )



def send_response(req_id: int, result: dict = None, error: dict = None):
    response = {
        "jsonrpc": "2.0",
        "id": req_id
    }
    if result is not None:
        response["result"] = result
    if error is not None:
        response["error"] = error
        
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()

def main():
    sys.stderr.write("Starting Workspace MCP server...\n")
    sys.stderr.flush()
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
                
            line = line.strip()
            if not line:
                continue
                
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                sys.stderr.write(f"Received invalid JSON: {line}\n")
                sys.stderr.flush()
                continue
                
            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            
            # If notification (no id), execute and skip sending response
            if req_id is None:
                continue
                
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "WorkspaceMcpServer",
                        "version": "1.0.0"
                    }
                }
                send_response(req_id, result=result)
                
            elif method == "tools/list":
                tools = [
                    {
                        "name": "calculate",
                        "description": "Safely evaluates mathematical expressions (e.g. 2 + 2, sin(pi/2)).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "expression": {
                                    "type": "string",
                                    "description": "Arithmetic math expression to calculate"
                                }
                            },
                            "required": ["expression"]
                        }
                    },
                    {
                        "name": "add_expense",
                        "description": "Add a new expense entry. Category accepts natural language (e.g. 'fooding', 'fast food', 'lunch', 'bf', 'lun', 'dnnr', 'coupon', 'groceries') — they are all normalised to canonical categories automatically. Optionally include a date (ISO format YYYY-MM-DD or natural text like '2026-07-02').",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "amount": {
                                    "type": "number",
                                    "description": "The expense amount in rupees"
                                },
                                "description": {
                                    "type": "string",
                                    "description": "What was bought or the expense label"
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Category — accepts informal names like 'fooding', 'fast food', 'lunch', 'bf', 'coupon', 'groceries', 'transport', 'bills', etc."
                                },
                                "date": {
                                    "type": "string",
                                    "description": "Optional date of the expense, e.g. '2026-07-02' or '2nd July 2026'"
                                }
                            },
                            "required": ["amount", "description"]
                        }
                    },
                    {
                        "name": "get_expenses",
                        "description": "Retrieve tracked expenses and calculate total spending. Supports filtering by category (accepts informal names like 'fooding', 'food', 'fast food') and/or by date.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "description": "Optional category filter — accepts 'fooding', 'food', 'fast food', 'lunch', 'transport', 'bills', etc."
                                },
                                "date": {
                                    "type": "string",
                                    "description": "Optional date filter e.g. '2026-07-02'"
                                }
                            }
                        }
                    },
                    {
                        "name": "summarize_expenses",
                        "description": "Show a full breakdown of all expenses grouped by category with per-category subtotals and a grand total. Use this when the user asks for overall spending or a complete summary.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    },
                    {
                        "name": "create_reminder",
                        "description": "Create a calendar reminder.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "time": {
                                    "type": "string",
                                    "description": "Time of the reminder (e.g., tomorrow at 10 AM)"
                                },
                                "text": {
                                    "type": "string",
                                    "description": "The reminder description"
                                }
                            },
                            "required": ["time", "text"]
                        }
                    },
                    {
                        "name": "get_reminders",
                        "description": "Retrieve all active calendar reminders.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    },
                    {
                        "name": "send_email",
                        "description": "Send a notification email.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "to": {
                                    "type": "string",
                                    "description": "Recipient email"
                                },
                                "subject": {
                                    "type": "string",
                                    "description": "Email subject"
                                },
                                "body": {
                                    "type": "string",
                                    "description": "Email body content"
                                }
                            },
                            "required": ["to", "subject", "body"]
                        }
                    }
                ]
                send_response(req_id, result={"tools": tools})
                
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    arguments = {}

                user_id = arguments.get("user_id") or params.get("user_id") or "default"
                currency = arguments.get("currency") or arguments.get("curr") or "₹"

                if tool_name == "calculate":
                    expr = (
                        arguments.get("expression") or
                        arguments.get("expr") or
                        arguments.get("formula") or
                        arguments.get("math_expression") or ""
                    )
                    calc_result = calculate(expr)
                    result = {"content": [{"type": "text", "text": calc_result}]}
                    send_response(req_id, result=result)
                elif tool_name == "add_expense":
                    amount_val = None
                    for key in ("amount", "cost", "price"):
                        if key in arguments:
                            amount_val = arguments[key]
                            break
                    amount = float(amount_val if amount_val is not None else 0)
                    description = (
                        arguments.get("description") or
                        arguments.get("desc") or
                        arguments.get("item") or
                        arguments.get("title") or ""
                    )
                    category = arguments.get("category") or arguments.get("cat") or "food"
                    date = arguments.get("date") or arguments.get("when") or None
                    res_str = add_expense(amount, description, category, date, currency=currency, user_id=user_id)
                    result = {"content": [{"type": "text", "text": res_str}]}
                    send_response(req_id, result=result)
                elif tool_name == "get_expenses":
                    category = arguments.get("category") or arguments.get("cat")
                    date = arguments.get("date") or arguments.get("when")
                    res_str = get_expenses(category, date, user_id=user_id)
                    result = {"content": [{"type": "text", "text": res_str}]}
                    send_response(req_id, result=result)
                elif tool_name == "summarize_expenses":
                    res_str = summarize_expenses(user_id=user_id)
                    result = {"content": [{"type": "text", "text": res_str}]}
                    send_response(req_id, result=result)
                elif tool_name == "create_reminder":
                    time_val = arguments.get("time") or arguments.get("when") or arguments.get("reminder_time") or ""
                    text = arguments.get("text") or arguments.get("reminder") or arguments.get("description") or ""
                    res_str = create_reminder(time_val, text, user_id=user_id)
                    result = {"content": [{"type": "text", "text": res_str}]}
                    send_response(req_id, result=result)
                elif tool_name == "get_reminders":
                    res_str = get_reminders(user_id=user_id)
                    result = {"content": [{"type": "text", "text": res_str}]}
                    send_response(req_id, result=result)
                elif tool_name == "send_email":
                    to = arguments.get("to") or arguments.get("recipient") or arguments.get("email") or ""
                    subject = arguments.get("subject") or arguments.get("title") or "Notification"
                    body = arguments.get("body") or arguments.get("message") or arguments.get("content") or ""
                    res_str = send_email(to, subject, body, user_id=user_id)
                    result = {"content": [{"type": "text", "text": res_str}]}
                    send_response(req_id, result=result)
                else:
                    error = {
                        "code": -32601,
                        "message": f"Tool '{tool_name}' not found."
                    }
                    send_response(req_id, error=error)
            else:
                error = {
                    "code": -32601,
                    "message": f"Method '{method}' not found."
                }
                send_response(req_id, error=error)
        except Exception as e:
            sys.stderr.write(f"Exception in calculator server main loop: {str(e)}\n")
            sys.stderr.flush()
            if req_id is not None:
                error = {"code": -32603, "message": f"Internal server error: {str(e)}"}
                send_response(req_id, error=error)
            continue

if __name__ == "__main__":
    main()
