import time
import httpx
import os


class HelpdeskError(Exception):
    def __init__(self, status: int, code: str, detail: str = ""):
        self.status = status
        self.code = code
        self.detail = detail
        super().__init__(f"HTTP {status} {code}: {detail}")


class AlreadyHandledError(HelpdeskError):
    pass


class HelpdeskClient:
    MAX_RETRIES = 5
    REQUEST_GAP = 0.22  # stay under 5 req/s

    def __init__(self):
        self.base_url = os.environ["HELPDESK_URL"].rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {os.environ['HELPDESK_KEY']}",
            "X-Candidate-Email": os.environ["CANDIDATE_EMAIL"],
            "Content-Type": "application/json",
        }
        self._last_request_at = time.monotonic()
        self._client = httpx.Client(timeout=30.0)

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.REQUEST_GAP:
            time.sleep(self.REQUEST_GAP - elapsed)
        self._last_request_at = time.monotonic()

    def _request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        for attempt in range(self.MAX_RETRIES):
            self._throttle()
            resp = self._client.request(method, url, headers=self.headers, json=json_body)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 2))
                time.sleep(wait)
                continue

            if resp.status_code == 503:
                time.sleep(2 ** attempt)
                continue

            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            code = body.get("error", str(resp.status_code))
            detail = body.get("message", resp.text[:200])

            if resp.status_code == 409:
                raise AlreadyHandledError(409, code, detail)

            raise HelpdeskError(resp.status_code, code, detail)

        raise HelpdeskError(503, "max_retries", f"Failed after {self.MAX_RETRIES} retries on {path}")

    def get_status(self) -> dict:
        return self._request("GET", "/status")

    def get_examples(self) -> list[dict]:
        return self._request("GET", "/examples")

    def get_tickets(self, status: str = "open") -> list[dict]:
        tickets = []
        cursor = None
        while True:
            path = f"/tickets?limit=10&status={status}"
            if cursor:
                path += f"&cursor={cursor}"
            data = self._request("GET", path)
            tickets.extend(data.get("tickets", []))
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return tickets

    def get_ticket(self, ticket_id: str) -> dict:
        return self._request("GET", f"/tickets/{ticket_id}")

    def reply(self, ticket_id: str, decision: dict) -> dict:
        return self._request("POST", f"/tickets/{ticket_id}/reply", decision)

    def handoff(self, ticket_id: str, decision: dict) -> dict:
        return self._request("POST", f"/tickets/{ticket_id}/handoff", decision)

    def close(self, ticket_id: str, decision: dict) -> dict:
        return self._request("POST", f"/tickets/{ticket_id}/close", decision)

    def reset_practice(self) -> dict:
        return self._request("POST", "/practice/reset")

    def close_connection(self):
        self._client.close()
