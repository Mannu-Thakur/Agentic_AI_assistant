import sys
import json
import math
import os

# Database file in the same folder
STORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_store.json")

def load_store():
    if not os.path.exists(STORE_FILE):
        return {"expenses": [], "reminders": [], "emails": []}
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"expenses": [], "reminders": [], "emails": []}

def save_store(store):
    try:
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
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


def calculate(expression: str) -> str:
    """
    Safely evaluate basic mathematical expressions.
    """
    allowed_chars = set("0123456789+-*/(). \t")
    safe_dict = {
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "exp": math.exp,
        "sqrt": math.sqrt,
        "pi": math.pi,
        "e": math.e
    }
    
    # Strip known safe math function names before character validation
    temp_expr = expression
    for k in safe_dict.keys():
        temp_expr = temp_expr.replace(k, "")
        
    if not all(c in allowed_chars for c in temp_expr):
        return "Error: Expression contains forbidden characters or dangerous operations."
        
    try:
        # Evaluate math expression safely without builtins
        val = eval(expression, {"__builtins__": None}, safe_dict)
        return str(val)
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"

def add_expense(amount: float, description: str, category: str = "food", date: str = None) -> str:
    store = load_store()
    canonical_cat = normalize_category(category)
    expense = {
        "amount": amount,
        "description": description,
        "category": canonical_cat,
        "date": date or "",          # ISO date string e.g. "2026-07-02", or empty
    }
    store["expenses"].append(expense)
    save_store(store)
    date_str = f" on {date}" if date else ""
    return f"✅ Added expense: ₹{amount} for '{description}' (Category: {canonical_cat}{date_str})."

def get_expenses(category: str = None, date: str = None) -> str:
    store = load_store()
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
    details = "\n".join(
        f"  • ₹{e['amount']} — {e['description']} [{e['category']}]"
        + (f" on {e['date']}" if e.get("date") else "")
        for e in expenses
    )
    filter_desc = []
    if category:
        filter_desc.append(f"category '{normalize_category(category)}'")
    if date:
        filter_desc.append(f"date '{date}'")
    header = f"Expenses{' (' + ', '.join(filter_desc) + ')' if filter_desc else ''}:"
    return f"{header}\n{details}\n\n💰 Total spent: ₹{total:.2f}"

def summarize_expenses() -> str:
    """Return a summary of all expenses grouped by category with per-category totals."""
    store = load_store()
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
    for cat, items in sorted(groups.items()):
        cat_total = sum(float(x["amount"]) for x in items)
        grand_total += cat_total
        lines.append(f"\n📂 {cat.upper()} — ₹{cat_total:.2f}")
        for x in items:
            date_str = f" ({x['date']})" if x.get("date") else ""
            lines.append(f"    • ₹{x['amount']} — {x['description']}{date_str}")

    return "📊 Expense Summary:\n" + "\n".join(lines) + f"\n\n💰 Grand Total: ₹{grand_total:.2f}"

def create_reminder(time: str, text: str) -> str:
    store = load_store()
    reminder = {
        "time": time,
        "text": text
    }
    store["reminders"].append(reminder)
    save_store(store)
    return f"✅ Reminder set for {time}: '{text}'."

def send_email(to: str, subject: str, body: str) -> str:
    store = load_store()
    email = {
        "to": to,
        "subject": subject,
        "body": body
    }
    store["emails"].append(email)
    save_store(store)
    return f"✅ Email sent to {to} with subject '{subject}'."


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
                
                if tool_name == "calculate":
                    expr = arguments.get("expression", "")
                    calc_result = calculate(expr)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": calc_result
                            }
                        ]
                    }
                    send_response(req_id, result=result)
                elif tool_name == "add_expense":
                    amount = float(arguments.get("amount", 0))
                    description = arguments.get("description", "")
                    category = arguments.get("category", "food")
                    date = arguments.get("date", None)
                    res_str = add_expense(amount, description, category, date)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": res_str
                            }
                        ]
                    }
                    send_response(req_id, result=result)
                elif tool_name == "get_expenses":
                    category = arguments.get("category")
                    date = arguments.get("date")
                    res_str = get_expenses(category, date)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": res_str
                            }
                        ]
                    }
                    send_response(req_id, result=result)
                elif tool_name == "summarize_expenses":
                    res_str = summarize_expenses()
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": res_str
                            }
                        ]
                    }
                    send_response(req_id, result=result)
                elif tool_name == "create_reminder":
                    time_val = arguments.get("time", "")
                    text = arguments.get("text", "")
                    res_str = create_reminder(time_val, text)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": res_str
                            }
                        ]
                    }
                    send_response(req_id, result=result)
                elif tool_name == "send_email":
                    to = arguments.get("to", "")
                    subject = arguments.get("subject", "")
                    body = arguments.get("body", "")
                    res_str = send_email(to, subject, body)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": res_str
                            }
                        ]
                    }
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
            break

if __name__ == "__main__":
    main()
