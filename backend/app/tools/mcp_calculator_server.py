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

def add_expense(amount: float, description: str, category: str = "food") -> str:
    store = load_store()
    expense = {
        "amount": amount,
        "description": description,
        "category": category
    }
    store["expenses"].append(expense)
    save_store(store)
    return f"Successfully added expense: ₹{amount} for '{description}' (Category: {category})."

def get_expenses(category: str = None) -> str:
    store = load_store()
    expenses = store["expenses"]
    if category:
        expenses = [e for e in expenses if e["category"].lower() == category.lower()]
    if not expenses:
        return f"No expenses found{f' for category {category}' if category else ''}."
    
    total = sum(float(e["amount"]) for e in expenses)
    details = "\n".join(f"- ₹{e['amount']}: {e['description']} ({e['category']})" for e in expenses)
    return f"Expenses:\n{details}\nTotal spent: ₹{total:.2f}"

def create_reminder(time: str, text: str) -> str:
    store = load_store()
    reminder = {
        "time": time,
        "text": text
    }
    store["reminders"].append(reminder)
    save_store(store)
    return f"Successfully created reminder for {time}: '{text}'."

def send_email(to: str, subject: str, body: str) -> str:
    store = load_store()
    email = {
        "to": to,
        "subject": subject,
        "body": body
    }
    store["emails"].append(email)
    save_store(store)
    return f"Successfully sent email to {to} with subject '{subject}'."

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
    sys.stderr.write("Starting Mock Calculator & Workspace MCP server...\n")
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
                        "name": "MockWorkspaceMcpServer",
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
                        "description": "Add a new expense to track spending (e.g. dinner, groceries).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "amount": {
                                    "type": "number",
                                    "description": "The expense amount"
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Description of what was bought"
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Category of the expense (e.g. food, transport, bills)"
                                }
                            },
                            "required": ["amount", "description"]
                        }
                    },
                    {
                        "name": "get_expenses",
                        "description": "Retrieve tracked expenses and total spending.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "description": "Optional category filter"
                                }
                            }
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
                    res_str = add_expense(amount, description, category)
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
                    res_str = get_expenses(category)
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
