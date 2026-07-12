import sys
import json
import math

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
    sys.stderr.write("Starting Mock Calculator MCP server...\n")
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
                        "name": "MockCalculatorMcpServer",
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
