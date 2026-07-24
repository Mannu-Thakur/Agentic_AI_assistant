import threading
from collections import Counter
from typing import List

class MetricsCollector:
    def __init__(self):
        self.request_counter = Counter()
        self.request_durations: List[float] = []
        self.tool_counter = Counter()
        self.db_errors = 0
        self.lock = threading.Lock()

    def record_request(self, method: str, path: str, status: int, duration_ms: float):
        """Records HTTP request method, path, response status, and duration."""
        with self.lock:
            self.request_counter[(method, path, status)] += 1
            self.request_durations.append(duration_ms)
            if len(self.request_durations) > 10000:
                self.request_durations.pop(0)

    def record_tool_call(self, tool_name: str, status: str):
        """Records agent tool executions by tool name and status."""
        with self.lock:
            self.tool_counter[(tool_name, status)] += 1

    def record_db_error(self):
        """Records database connection failures."""
        with self.lock:
            self.db_errors += 1

    def get_prometheus_exposition(self) -> str:
        """Formats collected metrics in standard Prometheus text format."""
        lines = []
        with self.lock:
            # 1. HTTP Requests Total
            lines.append("# HELP http_requests_total Total number of HTTP requests.")
            lines.append("# TYPE http_requests_total counter")
            for (method, path, status), count in self.request_counter.items():
                lines.append(f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

            # 2. Average Latency
            if self.request_durations:
                avg_dur = sum(self.request_durations) / len(self.request_durations)
                max_dur = max(self.request_durations)
            else:
                avg_dur = 0.0
                max_dur = 0.0
            
            lines.append("# HELP http_request_duration_ms_average Average HTTP request duration in milliseconds.")
            lines.append("# TYPE http_request_duration_ms_average gauge")
            lines.append(f"http_request_duration_ms_average {avg_dur:.2f}")

            lines.append("# HELP http_request_duration_ms_max Maximum HTTP request duration in milliseconds.")
            lines.append("# TYPE http_request_duration_ms_max gauge")
            lines.append(f"http_request_duration_ms_max {max_dur:.2f}")

            # 3. Tool Executions Total
            lines.append("# HELP tool_executions_total Total number of agent tool calls.")
            lines.append("# TYPE tool_executions_total counter")
            for (tool_name, status), count in self.tool_counter.items():
                lines.append(f'tool_executions_total{{tool="{tool_name}",status="{status}"}} {count}')

            # 4. Database Connection Errors
            lines.append("# HELP db_connection_errors_total Total database connection errors.")
            lines.append("# TYPE db_connection_errors_total counter")
            lines.append(f"db_connection_errors_total {self.db_errors}")

        return "\n".join(lines) + "\n"

metrics_collector = MetricsCollector()
