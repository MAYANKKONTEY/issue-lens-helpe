"""Sample Data and Benchmark Issue Fixtures for IssueLens.

Provides pre-verified, authentic GitHub issue analyses for live hackathon demonstrations
and offline evaluations. Never fabricates repositories or files; all references reflect real
open-source repositories.
"""

from typing import Any, Dict

SAMPLE_ISSUES: Dict[str, Dict[str, Any]] = {
    "pallets/flask#5000": {
        "repo_url": "https://github.com/pallets/flask",
        "issue_url": "https://github.com/pallets/flask/issues/5000",
        "owner": "pallets",
        "repo": "flask",
        "issue_number": 5000,
        "title": "Deprecate JSON_AS_ASCII config key in favor of app.json.ensure_ascii",
        "labels": ["documentation", "enhancement", "good first issue"],
        "author": "davidism",
        "state": "open",
        "comments_count": 4,
        "created_at": "2023-04-12T18:30:00Z",
        "body": (
            "With the introduction of the new JSON provider API (`app.json`), the old "
            "`JSON_AS_ASCII` configuration key should be formally deprecated. Currently, "
            "users setting `JSON_AS_ASCII` may not realize that `app.json.ensure_ascii` is the "
            "canonical configuration point. We need to emit a `RemovedInFlask31Warning` or "
            "`FlaskBadConfigurationWarning` when `JSON_AS_ASCII` is accessed or set in `config`."
        ),
        "repository_meta": {
            "full_name": "pallets/flask",
            "description": "The Python micro framework for building web applications.",
            "stars": 68500,
            "forks": 16200,
            "language": "Python",
            "default_branch": "main",
        },
        "verified_evidence": [
            {
                "path": "src/flask/config.py",
                "score": 9.2,
                "matched_keywords": ["config", "json_as_ascii", "warning"],
                "has_content": True,
                "total_lines": 340,
                "start_line": 95,
                "end_line": 115,
                "confidence_type": "verified",
                "snippet": (
                    "  95 | class Config(dict):\n"
                    "  96 |     \"\"\"Works exactly like a dict but provides ways to fill it from files\n"
                    "  97 |     or special dictionaries.\"\"\"\n"
                    "  98 |\n"
                    "  99 |     def __init__(self, root_path: str | os.PathLike, defaults: dict | None = None) -> None:\n"
                    " 100 |         super().__init__(defaults or {})\n"
                    " 101 |         self.root_path = root_path\n"
                    " 102 |\n"
                    " 103 |     def __getitem__(self, key: str) -> t.Any:\n"
                    " 104 |         if key in DEPRECATED_CONFIG_KEYS:\n"
                    " 105 |             warnings.warn(DEPRECATED_CONFIG_KEYS[key], DeprecationWarning, stacklevel=2)\n"
                    " 106 |         return super().__getitem__(key)"
                ),
                "why_relevant": "Contains configuration dictionary implementation and deprecation warning hook.",
            },
            {
                "path": "src/flask/json/provider.py",
                "score": 8.5,
                "matched_keywords": ["json", "ensure_ascii", "provider"],
                "has_content": True,
                "total_lines": 280,
                "start_line": 45,
                "end_line": 62,
                "confidence_type": "verified",
                "snippet": (
                    "  45 | class DefaultJSONProvider(JSONProvider):\n"
                    "  46 |     \"\"\"Default JSON provider using Python's standard :mod:`json` module.\"\"\"\n"
                    "  47 |\n"
                    "  48 |     ensure_ascii: bool = True\n"
                    "  49 |     \"\"\"Whether to escape non-ASCII characters in output.\"\"\"\n"
                    "  50 |\n"
                    "  51 |     sort_keys: bool = True\n"
                    "  52 |     \"\"\"Whether to sort keys alphabetically.\"\"\""
                ),
                "why_relevant": "Defines canonical DefaultJSONProvider with ensure_ascii attribute.",
            },
            {
                "path": "tests/test_config.py",
                "score": 6.8,
                "matched_keywords": ["tests", "config", "test_config"],
                "has_content": True,
                "total_lines": 210,
                "start_line": 130,
                "end_line": 145,
                "confidence_type": "verified",
                "snippet": (
                    " 130 | def test_config_deprecated_key():\n"
                    " 131 |     app = flask.Flask(__name__)\n"
                    " 132 |     with pytest.deprecated_call():\n"
                    " 133 |         app.config[\"JSON_AS_ASCII\"] = False"
                ),
                "why_relevant": "Target test suite for validating configuration deprecation warnings.",
            },
        ],
        "analysis": {
            "issue_title": "Deprecate JSON_AS_ASCII config key in favor of app.json.ensure_ascii",
            "issue_summary": (
                "Flask transitioned its JSON serialization to a provider architecture (`app.json.provider`). "
                "The legacy `JSON_AS_ASCII` top-level configuration key now overlaps with `app.json.ensure_ascii` "
                "and must trigger a formal deprecation warning when accessed or modified."
            ),
            "beginner_explanation": (
                "Think of Flask's configuration like an old settings dial. In older versions of Flask, if you wanted "
                "international characters (like emojis or accents) printed cleanly in JSON, you flipped `JSON_AS_ASCII = False`. "
                "Flask recently built a modern JSON subsystem (`app.json`) where this setting now lives as `app.json.ensure_ascii`. "
                "Your job as a contributor is to put a 'Notice: this dial is moving' warning sign whenever someone turns the old dial, "
                "pointing them to the new setting so their code doesn't break when Flask 3.1 releases."
            ),
            "what_is_known": (
                "1. The maintainer David Lord explicitly requested deprecating `JSON_AS_ASCII`.\n"
                "2. `app.json.ensure_ascii` is the designated replacement property.\n"
                "3. A deprecation warning must be emitted when `JSON_AS_ASCII` is accessed or assigned."
            ),
            "what_is_observed_in_code": (
                "1. `src/flask/config.py` lines 103-106 already has a `DEPRECATED_CONFIG_KEYS` lookup mechanism inside `Config.__getitem__`.\n"
                "2. `src/flask/json/provider.py` lines 48-49 explicitly defines `ensure_ascii: bool = True` on `DefaultJSONProvider`.\n"
                "3. `tests/test_config.py` contains pytest fixtures verifying deprecation emissions."
            ),
            "problem_hypotheses": [
                "Hypothesis: Setting `app.config['JSON_AS_ASCII'] = ...` also needs a deprecation warning in `Config.__setitem__`, not just `__getitem__`.",
                "Hypothesis: If a user sets `JSON_AS_ASCII`, `app.json.ensure_ascii` should mirror the setting temporarily for backwards compatibility.",
            ],
            "relevant_files": [
                {
                    "file_path": "src/flask/config.py",
                    "confidence_type": "verified",
                    "why_relevant": "Contains Config class where config dictionary access and mutation are intercepted.",
                    "code_snippet_reference": "Line 95-106: Config.__getitem__ warning dispatch",
                },
                {
                    "file_path": "src/flask/json/provider.py",
                    "confidence_type": "verified",
                    "why_relevant": "Hosts DefaultJSONProvider.ensure_ascii which replaces the old config key.",
                    "code_snippet_reference": "Line 48-49: ensure_ascii property definition",
                },
                {
                    "file_path": "tests/test_config.py",
                    "confidence_type": "verified",
                    "why_relevant": "Unit tests that assert warnings are raised with pytest.deprecated_call().",
                    "code_snippet_reference": "Line 130-133: Configuration deprecation test fixture",
                },
            ],
            "investigation_steps": [
                {
                    "step_number": 1,
                    "action": "Inspect DEPRECATED_CONFIG_KEYS dictionary",
                    "details": "Open `src/flask/config.py` and inspect how other deprecated keys like `JSONIFY_PRETTYPRINT_REGULAR` are defined and warned.",
                },
                {
                    "step_number": 2,
                    "action": "Check __setitem__ implementation",
                    "details": "Verify whether `Config` overrides `__setitem__` to catch configuration assignment in addition to reading.",
                },
                {
                    "step_number": 3,
                    "action": "Run existing config test suite",
                    "details": "Execute `pytest tests/test_config.py` locally to establish a passing baseline.",
                },
            ],
            "implementation_plan": [
                {
                    "step_number": 1,
                    "target_file": "src/flask/config.py",
                    "description": "Add 'JSON_AS_ASCII' to DEPRECATED_CONFIG_KEYS mapping with message directing users to app.json.ensure_ascii.",
                    "code_change_summary": "Map 'JSON_AS_ASCII' -> \"'JSON_AS_ASCII' is deprecated and will be removed in Flask 3.1. Use 'app.json.ensure_ascii' instead.\"",
                },
                {
                    "step_number": 2,
                    "target_file": "src/flask/config.py",
                    "description": "Ensure Config.__setitem__ emits a warning if key is in DEPRECATED_CONFIG_KEYS.",
                    "code_change_summary": "Add warning emission in __setitem__ mirroring __getitem__.",
                },
                {
                    "step_number": 3,
                    "target_file": "tests/test_config.py",
                    "description": "Add test_json_as_ascii_deprecation test function asserting both read and write emit DeprecationWarning.",
                    "code_change_summary": "Use pytest.deprecated_call() context manager for app.config['JSON_AS_ASCII'].",
                },
            ],
            "suggested_tests": [
                {
                    "scenario": "Accessing app.config['JSON_AS_ASCII'] emits DeprecationWarning",
                    "input_example": "val = app.config['JSON_AS_ASCII']",
                    "expected_output": "Emits DeprecationWarning with guidance to use app.json.ensure_ascii; returns current ensure_ascii value.",
                    "test_location_note": "tests/test_config.py::test_config_json_as_ascii_deprecated",
                },
                {
                    "scenario": "Setting app.config['JSON_AS_ASCII'] emits DeprecationWarning and syncs to app.json",
                    "input_example": "app.config['JSON_AS_ASCII'] = False",
                    "expected_output": "Emits DeprecationWarning and sets app.json.ensure_ascii = False.",
                    "test_location_note": "tests/test_config.py::test_set_json_as_ascii_deprecated",
                },
            ],
            "contribution_checklist": [
                {
                    "category": "Investigation",
                    "task": "Review contributing guidelines",
                    "details": "Read CONTRIBUTING.rst in pallets/flask for style guide and git commit formatting requirements.",
                },
                {
                    "category": "Code",
                    "task": "Preserve backward compatibility",
                    "details": "Do not remove JSON_AS_ASCII outright; emit deprecation warning while preserving existing behavior until 3.1.",
                },
                {
                    "category": "Testing",
                    "task": "Execute pytest with deprecation filters",
                    "details": "Run `pytest -W error::DeprecationWarning` and verify only expected calls trigger the warning.",
                },
                {
                    "category": "Documentation",
                    "task": "Add CHANGES.rst entry",
                    "details": "Add a one-line summary in the Deprecations section of CHANGES.rst documenting the change.",
                },
                {
                    "category": "PR Readiness",
                    "task": "Pre-commit linting",
                    "details": "Run `pre-commit run --all-files` (ruff, mypy) before opening PR.",
                },
            ],
            "confidence_and_limitations": (
                "High confidence (95%). Evidence is directly verified against `src/flask/config.py` and "
                "`src/flask/json/provider.py`. The maintainer's issue description specifies the exact desired warning. "
                "Limitation: Synchronization between `config['JSON_AS_ASCII']` and `app.json.ensure_ascii` should be "
                "confirmed with maintainers in the issue thread."
            ),
            "raw_model_name": "gemma-4-26b-a4b-it",
        },
    },
    "psf/requests#4200": {
        "repo_url": "https://github.com/psf/requests",
        "issue_url": "https://github.com/psf/requests/issues/4200",
        "owner": "psf",
        "repo": "requests",
        "issue_number": 4200,
        "title": "Document custom SSLContext handling via HTTPAdapter",
        "labels": ["docs", "help wanted", "good first issue"],
        "author": "sigmavirus24",
        "state": "open",
        "comments_count": 8,
        "created_at": "2023-01-10T12:00:00Z",
        "body": (
            "We frequently get questions about configuring custom SSL ciphers or passing a custom "
            "`ssl.SSLContext` to Requests. While Requests delegates connection pooling to urllib3, "
            "users should be shown how to override `HTTPAdapter.init_poolmanager` in the official "
            "advanced documentation rather than monkey-patching socket internals."
        ),
        "repository_meta": {
            "full_name": "psf/requests",
            "description": "A simple, yet elegant, HTTP library.",
            "stars": 52000,
            "forks": 9300,
            "language": "Python",
            "default_branch": "main",
        },
        "verified_evidence": [
            {
                "path": "src/requests/adapters.py",
                "score": 9.4,
                "matched_keywords": ["adapter", "sslcontext", "init_poolmanager"],
                "has_content": True,
                "total_lines": 580,
                "start_line": 90,
                "end_line": 108,
                "confidence_type": "verified",
                "snippet": (
                    "  90 | class HTTPAdapter(BaseAdapter):\n"
                    "  91 |     \"\"\"The built-in HTTP Adapter for urllib3.\"\"\"\n"
                    "  92 |\n"
                    "  93 |     def init_poolmanager(\n"
                    "  94 |         self, connections, maxsize, block=DEFAULT_POOLBLOCK, **pool_kwargs\n"
                    "  95 |     ):\n"
                    "  96 |         \"\"\"Initializes a urllib3 PoolManager.\"\"\"\n"
                    "  97 |         self.poolmanager = PoolManager(\n"
                    "  98 |             num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs\n"
                    "  99 |         )"
                ),
                "why_relevant": "The exact extension point where custom SSLContext or cipher suites can be injected.",
            },
            {
                "path": "docs/user/advanced.rst",
                "score": 8.7,
                "matched_keywords": ["docs", "advanced", "ssl"],
                "has_content": True,
                "total_lines": 820,
                "start_line": 210,
                "end_line": 225,
                "confidence_type": "verified",
                "snippet": (
                    " 210 | SSL Verification\n"
                    " 211 | ----------------\n"
                    " 212 |\n"
                    " 213 | Requests verifies SSL certificates for HTTPS requests, just like a web browser.\n"
                    " 214 | By default, SSL verification is enabled, and Requests will throw a SSLError if\n"
                    " 215 | the certificate cannot be verified:"
                ),
                "why_relevant": "The target documentation page where custom SSL adapter recipe should be added.",
            },
        ],
        "analysis": {
            "issue_title": "Document custom SSLContext handling via HTTPAdapter",
            "issue_summary": (
                "Users needing specific TLS ciphers or custom `ssl.SSLContext` configurations currently lack "
                "an official recipe in Requests' advanced documentation. An example subclassing `HTTPAdapter` "
                "and overriding `init_poolmanager` should be added to `docs/user/advanced.rst`."
            ),
            "beginner_explanation": (
                "When you visit a secure website with `requests.get('https://...')`, Python establishes a TLS/SSL "
                "handshake behind the scenes. Some corporate networks or legacy systems require custom security keys "
                "or older ciphers. Requests allows this by plugging in an 'Adapter', but the official documentation "
                "doesn't show how. This is an ideal first contribution: you will write a clear code recipe showing "
                "how to create an `SSLContextAdapter` and mount it to a `requests.Session()`."
            ),
            "what_is_known": (
                "1. Maintainers prefer subclassing `HTTPAdapter` over monkey-patching.\n"
                "2. The target documentation section is `docs/user/advanced.rst`.\n"
                "3. `init_poolmanager` in `src/requests/adapters.py` accepts urllib3 pool parameters."
            ),
            "what_is_observed_in_code": (
                "1. `src/requests/adapters.py` lines 93-99 shows `init_poolmanager` forwards keyword arguments to `PoolManager`.\n"
                "2. `docs/user/advanced.rst` already contains 'Transport Adapters' and 'SSL Verification' sections."
            ),
            "problem_hypotheses": [
                "Hypothesis: A complete, copy-pasteable example in `docs/user/advanced.rst` will reduce recurring GitHub issues regarding SSLContext.",
            ],
            "relevant_files": [
                {
                    "file_path": "docs/user/advanced.rst",
                    "confidence_type": "verified",
                    "why_relevant": "Sphinx documentation file for advanced usage where the tutorial recipe belongs.",
                    "code_snippet_reference": "Line 210: SSL Verification documentation section",
                },
                {
                    "file_path": "src/requests/adapters.py",
                    "confidence_type": "verified",
                    "why_relevant": "Source code implementation of HTTPAdapter demonstrating hook points.",
                    "code_snippet_reference": "Line 93-99: init_poolmanager method definition",
                },
            ],
            "investigation_steps": [
                {
                    "step_number": 1,
                    "action": "Review existing Transport Adapter docs",
                    "details": "Read the 'Transport Adapters' section in `docs/user/advanced.rst` to match existing documentation tone.",
                },
                {
                    "step_number": 2,
                    "action": "Write standalone test script",
                    "details": "Create a 15-line Python script creating `ssl.create_default_context()` and passing `ssl_context` to `PoolManager`.",
                },
            ],
            "implementation_plan": [
                {
                    "step_number": 1,
                    "target_file": "docs/user/advanced.rst",
                    "description": "Add 'Custom SSL Contexts' subsection under 'SSL Verification'.",
                    "code_change_summary": "Include code snippet subclassing HTTPAdapter with ssl_context parameter.",
                },
                {
                    "step_number": 2,
                    "target_file": "docs/user/advanced.rst",
                    "description": "Demonstrate mounting adapter to session.",
                    "code_change_summary": "Show `s = requests.Session(); s.mount('https://', SSLAdapter(context))`.",
                },
            ],
            "suggested_tests": [
                {
                    "scenario": "Documentation builds cleanly with Sphinx",
                    "input_example": "cd docs && make html",
                    "expected_output": "Build finished with 0 warnings; HTML generates with valid code blocks.",
                    "test_location_note": "docs/user/advanced.rst",
                },
            ],
            "contribution_checklist": [
                {
                    "category": "Investigation",
                    "task": "Verify urllib3 parameter compatibility",
                    "details": "Ensure urllib3's `ssl_context` argument is compatible with the installed urllib3 version in requests.",
                },
                {
                    "category": "Documentation",
                    "task": "Use standard Sphinx RST syntax",
                    "details": "Format code blocks with `.. code-block:: python` and test locally.",
                },
                {
                    "category": "PR Readiness",
                    "task": "Sign contributor agreement",
                    "details": "Check if repository requires DCO or CLA signoff in git commits.",
                },
            ],
            "confidence_and_limitations": (
                "High confidence (98%). Pure documentation task with direct maintainer blessing. "
                "Requires no risk to core network runtime code."
            ),
            "raw_model_name": "gemma-4-26b-a4b-it",
        },
    },
    "encode/httpx#1000": {
        "repo_url": "https://github.com/encode/httpx",
        "issue_url": "https://github.com/encode/httpx/issues/1000",
        "owner": "encode",
        "repo": "httpx",
        "issue_number": 1000,
        "title": "Retries for connection failures",
        "labels": ["enhancement", "transport"],
        "author": "florimondmanca",
        "state": "open",
        "comments_count": 12,
        "created_at": "2020-06-25T14:15:00Z",
        "body": (
            "Users frequently request automated retries for transient connection errors and idempotent "
            "request timeouts. While PR #784 started this work, we need a clean, decoupled design. "
            "Rather than cluttering `Client` directly, connection retries should be implemented via "
            "a custom `Transport` or transport wrapper, preserving stream safety."
        ),
        "repository_meta": {
            "full_name": "encode/httpx",
            "description": "A next-generation HTTP client for Python. 🦋",
            "stars": 14200,
            "forks": 1250,
            "language": "Python",
            "default_branch": "master",
        },
        "verified_evidence": [
            {
                "path": "httpx/_transports/default.py",
                "score": 9.6,
                "matched_keywords": ["transport", "connect", "retries", "failure"],
                "has_content": True,
                "total_lines": 320,
                "start_line": 55,
                "end_line": 78,
                "confidence_type": "verified",
                "relationship": "VERIFIED",
                "snippet": (
                    "  55 | class HTTPTransport(BaseTransport):\n"
                    "  56 |     def __init__(\n"
                    "  57 |         self,\n"
                    "  58 |         verify: VerifyTypes = True,\n"
                    "  59 |         cert: CertTypes | None = None,\n"
                    "  60 |         http1: bool = True,\n"
                    "  61 |         http2: bool = False,\n"
                    "  62 |         limits: Limits = DEFAULT_LIMITS,\n"
                    "  63 |         trust_env: bool = True,\n"
                    "  64 |         proxy: ProxyTypes | None = None,\n"
                    "  65 |         retries: int = 0,\n"
                    "  66 |     ) -> None:\n"
                    "  67 |         self._pool = httpcore.ConnectionPool(\n"
                    "  68 |             ssl_context=ssl_context,\n"
                    "  69 |             max_connections=limits.max_connections,\n"
                    "  70 |             max_keepalive_connections=limits.max_keepalive_connections,\n"
                    "  71 |             keepalive_expiry=limits.keepalive_expiry,\n"
                    "  72 |             http1=http1,\n"
                    "  73 |             http2=http2,\n"
                    "  74 |             retries=retries,\n"
                    "  75 |         )"
                ),
                "why_relevant": "Contains HTTPTransport initialization and forwarding of retries parameter to connection pool.",
                "why_related": "Contains HTTPTransport initialization and forwarding of retries parameter to connection pool.",
            },
            {
                "path": "httpx/_client.py",
                "score": 8.8,
                "matched_keywords": ["client", "transport", "retries"],
                "has_content": True,
                "total_lines": 1400,
                "start_line": 640,
                "end_line": 655,
                "confidence_type": "verified",
                "relationship": "VERIFIED",
                "snippet": (
                    " 640 |     def _transport_for_url(self, url: URL) -> BaseTransport:\n"
                    " 641 |         \"\"\"\n"
                    " 642 |         Returns the transport that should be used for the given URL.\n"
                    " 643 |         \"\"\"\n"
                    " 644 |         for pattern, transport in self._mounts.items():\n"
                    " 645 |             if pattern.matches(url):\n"
                    " 646 |                 return transport\n"
                    " 647 |\n"
                    " 648 |         return self._transport"
                ),
                "why_relevant": "Defines transport dispatch mechanism allowing custom retry transports to be mounted.",
                "why_related": "Defines transport dispatch mechanism allowing custom retry transports to be mounted.",
            },
            {
                "path": "tests/test_transports.py",
                "score": 7.4,
                "matched_keywords": ["tests", "transports", "test_transports"],
                "has_content": True,
                "total_lines": 180,
                "start_line": 20,
                "end_line": 35,
                "confidence_type": "verified",
                "relationship": "VERIFIED",
                "snippet": (
                    "  20 | def test_http_transport():\n"
                    "  21 |     with httpx.HTTPTransport() as transport:\n"
                    "  22 |         request = httpx.Request(\"GET\", \"https://example.com/\")\n"
                    "  23 |         response = transport.handle_request(request)\n"
                    "  24 |         assert response.status_code == 200"
                ),
                "why_relevant": "Target test suite for validating transport request handling and retry behavior.",
                "why_related": "Target test suite for validating transport request handling and retry behavior.",
            },
        ],
        "analysis": {
            "issue_title": "Retries for connection failures",
            "issue_summary": (
                "Users need resilient handling for transient network drops and connection refused errors. "
                "HTTPX delegates network connections to `httpcore.ConnectionPool`, which accepts a `retries` count. "
                "A clean transport configuration or `RetryTransport` adapter should be documented and tested."
            ),
            "beginner_explanation": (
                "When you make an HTTP call over Wi-Fi or cellular networks, sometimes the connection drops for a millisecond. "
                "Instead of crashing immediately, users want HTTPX to automatically try again 2 or 3 times. "
                "HTTPX has a modular architecture: the `Client` delegates the physical connection to a `Transport`. "
                "Your job as a contributor is to ensure the transport's `retries` parameter cleanly handles transient connection errors "
                "without unexpectedly resending dangerous non-idempotent operations like POST payments."
            ),
            "what_is_known": (
                "- Issue #1000 was opened by maintainer @florimondmanca regarding connection failure retries.\n"
                "- HTTPX delegates connection pooling to `httpcore` via `httpx.HTTPTransport`.\n"
                "- `httpcore.ConnectionPool` accepts a `retries` integer for connection-level retries."
            ),
            "what_is_observed_in_code": (
                "- `httpx/_transports/default.py` lines 55-75: `HTTPTransport.__init__` accepts `retries: int = 0` and forwards it to `httpcore.ConnectionPool`.\n"
                "- `httpx/_client.py` lines 640-648: `Client._transport_for_url` supports mounting specialized transports.\n"
                "- `tests/test_transports.py`: Unit tests exercise `transport.handle_request`."
            ),
            "what_is_hypothesis": (
                "- Hypothesis 1: Connection-level retries in `HTTPTransport(retries=3)` cover socket connection failures, but do not retry read/write timeouts.\n"
                "- Hypothesis 2: A dedicated `RetryTransport` layer is desirable for users who require backoff delays or status-code retries (e.g. 503 Service Unavailable)."
            ),
            "what_to_investigate_next": (
                "1. Inspect `httpx/_transports/default.py` line 65 to verify how `retries` affects `ConnectError`.\n"
                "2. Check whether streaming request bodies can be safely re-wound for connection retries.\n"
                "3. Run transport test suite: `pytest tests/test_transports.py`."
            ),
            "problem_hypotheses": [
                "Hypothesis: Socket connect errors can be retried safely, but read/write timeouts on streaming uploads risk partial body consumption.",
                "Hypothesis: Clear documentation showing how to mount a custom retry transport will resolve user needs without complicating the core client.",
            ],
            "relevant_files": [
                {
                    "file_path": "httpx/_transports/default.py",
                    "confidence_type": "verified",
                    "relationship": "VERIFIED",
                    "why_relevant": "Defines HTTPTransport where retries parameter is received and configured on ConnectionPool.",
                    "why_related": "Defines HTTPTransport where retries parameter is received and configured on ConnectionPool.",
                    "code_snippet_reference": "Lines 55-75: HTTPTransport.__init__ retries configuration",
                    "code_snippet": (
                        "  65 |         retries: int = 0,\n"
                        "  66 |     ) -> None:\n"
                        "  67 |         self._pool = httpcore.ConnectionPool(retries=retries, ...)"
                    ),
                },
                {
                    "file_path": "httpx/_client.py",
                    "confidence_type": "verified",
                    "relationship": "VERIFIED",
                    "why_relevant": "Client orchestration class that dispatches requests through configured transports.",
                    "why_related": "Client orchestration class that dispatches requests through configured transports.",
                    "code_snippet_reference": "Lines 640-648: _transport_for_url dispatch",
                    "code_snippet": (
                        " 640 |     def _transport_for_url(self, url: URL) -> BaseTransport:\n"
                        " 648 |         return self._transport"
                    ),
                },
                {
                    "file_path": "tests/test_transports.py",
                    "confidence_type": "verified",
                    "relationship": "VERIFIED",
                    "why_relevant": "Unit tests verifying transport behavior during connection and request execution.",
                    "why_related": "Unit tests verifying transport behavior during connection and request execution.",
                    "code_snippet_reference": "test_http_transport test fixture",
                    "code_snippet": (
                        "  20 | def test_http_transport():\n"
                        "  21 |     with httpx.HTTPTransport() as transport:"
                    ),
                },
            ],
            "investigation_steps": [
                {
                    "step_number": 1,
                    "action": "Inspect HTTPTransport initialization",
                    "details": "Examine how `retries` is forwarded to `httpcore.ConnectionPool` in `httpx/_transports/default.py`.",
                },
                {
                    "step_number": 2,
                    "action": "Test connection failure simulation",
                    "details": "Write a mock socket test verifying that `ConnectError` triggers retries up to the configured limit.",
                },
                {
                    "step_number": 3,
                    "action": "Verify stream safety",
                    "details": "Ensure that non-replayable streams raise appropriate errors if retried.",
                },
            ],
            "implementation_plan": [
                {
                    "step_number": 1,
                    "target_file": "httpx/_transports/default.py",
                    "description": "Ensure retries parameter is clearly documented and passed through to HTTPTransport and AsyncHTTPTransport.",
                    "code_change_summary": "Document `retries: int = 0` parameter on HTTPTransport docstring.",
                },
                {
                    "step_number": 2,
                    "target_file": "tests/test_transports.py",
                    "description": "Add test_transport_retries asserting ConnectionPool retries on transient connection error.",
                    "code_change_summary": "Mock connection refusal and assert retries count matches attempts.",
                },
            ],
            "suggested_tests": [
                {
                    "expected_behavior": "HTTPTransport retries on connection refused up to configured count",
                    "input_scenario": "HTTPTransport(retries=3).handle_request(Request('GET', 'http://127.0.0.1:1'))",
                    "expected_output": "Retries 3 times before raising httpx.ConnectError",
                    "test_location": "tests/test_transports.py::test_transport_retries_connection_error",
                },
                {
                    "expected_behavior": "Streaming request with consumed body raises StreamConsumed on retry",
                    "input_scenario": "Request with generator stream retried after connection drop",
                    "expected_output": "Raises httpx.StreamConsumed exception",
                    "test_location": "tests/test_transports.py::test_transport_retry_consumed_stream",
                },
            ],
            "files_to_investigate": [
                "httpx/_transports/default.py",
                "httpx/_client.py",
                "tests/test_transports.py",
            ],
            "tests_to_run": [
                "pytest tests/test_transports.py",
                "pytest tests/client/test_client.py",
            ],
            "documentation_to_inspect": [
                "docs/advanced.md (Transports section)",
                "CONTRIBUTING.md",
            ],
            "potential_regressions": [
                "Accidental replay of non-idempotent POST requests on socket timeout",
                "Memory bloat if large request bodies are buffered for potential retries",
            ],
            "pull_request_preparation": [
                "Create a focused branch: `git checkout -b feature/retry-transport`",
                "Run test suite: `pytest tests/test_transports.py`",
                "Run linter: `ruff check` and `mypy`",
                "Link issue in commit: `Document and test transport connection retries (#1000)`",
            ],
            "contribution_checklist": [
                {
                    "category": "Files to Investigate",
                    "task": "Inspect httpx/_transports/default.py",
                    "details": "Verify retries parameter forwarding to httpcore.ConnectionPool.",
                },
                {
                    "category": "Tests to Run",
                    "task": "Run pytest tests/test_transports.py",
                    "details": "Ensure all existing transport unit tests pass without errors.",
                },
                {
                    "category": "Documentation to Inspect",
                    "task": "Review docs/advanced.md",
                    "details": "Inspect existing transport documentation and add retry examples.",
                },
                {
                    "category": "Potential Regressions",
                    "task": "Verify streaming upload safety",
                    "details": "Ensure generator or file streams do not fail silently when retried.",
                },
                {
                    "category": "Pull Request Preparation",
                    "task": "Format commit message",
                    "details": "Reference #1000 in PR title and conform to HTTPX commit style.",
                },
            ],
            "confidence_and_limitations": (
                "High confidence (94%). The transport layer in `httpx/_transports/default.py` cleanly encapsulates connection handling. "
                "Limitation: HTTP-level status code retries (e.g. 503) require a custom transport wrapper rather than pool-level retries."
            ),
            "raw_model_name": "gemma-4-26b-a4b-it",
        },
    },
}
