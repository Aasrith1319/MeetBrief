"""Offline glossary used by Explain Again when no LLM is configured (F22).

Each entry: definition (simple), example, analogy, steps, detail.
The meeting-specific context is always added separately from the transcript.
"""
from __future__ import annotations

GLOSSARY: dict[str, dict[str, object]] = {
    "database indexing": {
        "aliases": ["indexing", "index", "indexes", "indices", "database index"],
        "definition": "An index is an extra lookup structure a database keeps so it can find matching rows quickly instead of scanning every row.",
        "example": "If a users table is often searched by email, an index on the email column lets the database jump straight to the right user.",
        "analogy": "It is like the index at the back of a textbook: instead of reading every page to find a topic, you look it up and go straight to the page.",
        "steps": ["Find the queries that are slow and the columns they filter or sort on.",
                  "Create an index on those columns.",
                  "The database now looks values up in the index instead of scanning the table.",
                  "Measure query time again to confirm the improvement (indexes also make writes slightly slower)."],
        "detail": "Most relational databases use B-tree indexes, giving O(log n) lookups versus O(n) full-table scans. Trade-offs: extra storage, slower INSERT/UPDATE, and the planner only uses an index when the query's predicates match it (column order matters in composite indexes).",
    },
    "caching": {
        "aliases": ["cache", "caches", "cached", "redis", "memcached"],
        "definition": "Caching means keeping a copy of frequently used results in fast storage so they don't have to be computed or fetched again.",
        "example": "A product page's data can be stored in a cache for 60 seconds so thousands of visitors don't each hit the database.",
        "analogy": "Like keeping your most-used tools on your desk instead of walking to the storeroom every time.",
        "steps": ["Identify data that is read often but changes rarely.", "Store a copy in a fast cache (memory, Redis).",
                  "Serve reads from the cache; fall back to the source on a miss.", "Invalidate or expire entries when the data changes."],
        "detail": "Key design questions are cache invalidation strategy (TTL, write-through, write-behind), consistency guarantees, eviction policy (LRU/LFU) and hit-rate monitoring.",
    },
    "benchmark": {
        "aliases": ["benchmarking", "benchmarks", "benchmarked"],
        "definition": "A benchmark is a repeatable measurement of performance, such as how long a request takes, used to compare before and after a change.",
        "example": "Run the same 1,000 queries before and after adding an index and compare the average response time.",
        "analogy": "Like timing your run on the same route before and after new shoes, so you know whether the shoes actually helped.",
        "steps": ["Pick a representative workload.", "Measure the current performance.", "Apply the change.", "Measure again under the same conditions and compare."],
        "detail": "Good benchmarks control for warm-up, caching effects and variance; report percentiles (p50/p95/p99), not only averages.",
    },
    "latency": {
        "aliases": ["response time", "lag"],
        "definition": "Latency is the delay between asking for something and getting the answer.",
        "example": "If a page takes 800 ms to load after you click, its latency is 800 ms.",
        "analogy": "Like the time between ordering at a counter and receiving your coffee.",
        "steps": ["A request is sent.", "It travels over the network and is processed.", "The response comes back.", "The total time is the latency."],
        "detail": "Latency is usually reported as percentiles; tail latency (p99) often matters more for user experience than the average.",
    },
    "api": {
        "aliases": ["apis", "endpoint", "endpoints", "rest api"],
        "definition": "An API is a defined way for one program to ask another program for data or actions.",
        "example": "A weather app calls a weather service's API to get today's forecast.",
        "analogy": "Like a restaurant menu: it lists what you can order and how, without showing you the kitchen.",
        "steps": ["The client sends a request to an endpoint.", "The server validates it and does the work.", "The server returns a structured response (often JSON)."],
        "detail": "REST APIs map resources to URLs and HTTP verbs; contracts are often documented with OpenAPI, and versioning protects existing clients.",
    },
    "deployment": {
        "aliases": ["deploy", "deploying", "release", "rollout"],
        "definition": "Deployment is the process of putting a new version of software where users can use it.",
        "example": "After tests pass, the team deploys version 2.3 to the production servers.",
        "analogy": "Like restocking a shop's shelves with a new product line after it has been checked in the back room.",
        "steps": ["Build the new version.", "Run automated tests.", "Release it to a staging or small group first.", "Roll out to everyone and monitor."],
        "detail": "Strategies include blue-green, canary and rolling deployments; feature flags decouple deploy from release.",
    },
    "sprint": {
        "aliases": ["sprints", "iteration"],
        "definition": "A sprint is a short, fixed period (often two weeks) in which a team completes a planned set of work.",
        "example": "In this sprint the team plans to finish login and the profile page.",
        "analogy": "Like planning a two-week study block with a clear list of chapters to finish.",
        "steps": ["Plan the work.", "Build and test during the sprint.", "Demo the results.", "Reflect and plan the next sprint."],
        "detail": "In Scrum, sprints include planning, daily stand-ups, a review and a retrospective; scope is fixed during the sprint.",
    },
    "regression": {
        "aliases": ["regressions", "regression test", "regression testing"],
        "definition": "A regression is when something that used to work breaks after a change.",
        "example": "After a speed fix, the search page stopped showing results — that is a regression.",
        "analogy": "Like fixing a leaky tap and accidentally cutting the water to the kitchen.",
        "steps": ["Make a change.", "Re-run tests for existing features.", "If an old feature fails, fix the regression before shipping."],
        "detail": "Regression suites are automated tests run on every change (CI) to catch unintended behaviour changes early.",
    },
    "load balancer": {
        "aliases": ["load balancing", "load-balancer"],
        "definition": "A load balancer spreads incoming requests across several servers so no single server is overwhelmed.",
        "example": "10,000 users hit the site; the load balancer sends some to server A, some to B and some to C.",
        "analogy": "Like a host at a restaurant seating guests at different tables so no waiter is overloaded.",
        "steps": ["Requests arrive at the balancer.", "It picks a healthy server (round-robin, least connections, ...).", "It forwards the request and returns the response."],
        "detail": "Layer-4 vs layer-7 balancing, health checks, sticky sessions and TLS termination are common design choices.",
    },
    "microservices": {
        "aliases": ["microservice", "micro-services"],
        "definition": "Microservices is a way of building an application as many small, independent services that talk to each other.",
        "example": "An online store may have separate services for payments, search and inventory.",
        "analogy": "Like a food court with separate stalls, each specialising in one dish, instead of one giant kitchen.",
        "steps": ["Split the system by business capability.", "Give each service its own data and API.", "Deploy and scale each service independently."],
        "detail": "Benefits: independent deploys and scaling. Costs: network latency, distributed tracing, data consistency and operational overhead.",
    },
    "query": {
        "aliases": ["queries", "sql query", "sql"],
        "definition": "A query is a request to a database for specific data, often written in SQL.",
        "example": "SELECT name FROM users WHERE city = 'Hyderabad' asks for names of users in Hyderabad.",
        "analogy": "Like asking a librarian for all books by one author.",
        "steps": ["Write the question in SQL.", "The database plans how to find the data.", "It reads the needed rows and returns the result."],
        "detail": "Query planners choose between scans and index lookups; EXPLAIN shows the chosen plan and its estimated cost.",
    },
    "rag": {
        "aliases": ["retrieval-augmented generation", "retrieval augmented generation"],
        "definition": "RAG means first searching for relevant source text, then giving it to a language model so its answer is grounded in that text.",
        "example": "To answer 'who owns the indexing task?', the system retrieves the transcript line where the task was assigned and answers from it.",
        "analogy": "Like an open-book exam: you look up the relevant pages before writing your answer.",
        "steps": ["Split documents into chunks.", "Turn chunks and the question into vectors.", "Retrieve the most similar chunks.", "Generate an answer using only those chunks, citing them."],
        "detail": "Quality depends on chunking, embedding model, retrieval (dense, sparse or hybrid), re-ranking, and abstaining when evidence is weak.",
    },
    "embedding": {
        "aliases": ["embeddings", "vector", "vectors", "sentence embeddings"],
        "definition": "An embedding turns text into a list of numbers so that texts with similar meaning end up close together.",
        "example": "'The query is slow' and 'the database is lagging' get similar embeddings even with different words.",
        "analogy": "Like placing every sentence as a pin on a map where nearby pins mean similar ideas.",
        "steps": ["Feed text into an embedding model.", "Get a vector of numbers.", "Compare vectors with cosine similarity to find related text."],
        "detail": "Sentence-transformer models are trained with contrastive objectives; vector indexes (FAISS, HNSW) make nearest-neighbour search fast.",
    },
    "technical debt": {
        "aliases": ["tech debt"],
        "definition": "Technical debt is the future extra work caused by choosing a quick solution now instead of a better one.",
        "example": "Copy-pasting code to ship faster means every later fix must be made in several places.",
        "analogy": "Like borrowing money: it helps now, but you pay interest until you pay it back.",
        "steps": ["Take a shortcut to meet a deadline.", "The shortcut slows later work.", "Plan time to refactor and 'pay down' the debt."],
        "detail": "Teams track debt explicitly, prioritise by interest (how much it slows work) and reserve capacity each sprint for refactoring.",
    },
    "ci/cd": {
        "aliases": ["ci", "cd", "continuous integration", "continuous delivery", "pipeline"],
        "definition": "CI/CD is automation that tests every code change (CI) and delivers it to users quickly and safely (CD).",
        "example": "When a developer pushes code, tests run automatically and, if they pass, the app is deployed to staging.",
        "analogy": "Like a factory line that inspects every part automatically before it is packed and shipped.",
        "steps": ["Developer pushes a change.", "The pipeline builds and tests it.", "If green, it is deployed to staging/production."],
        "detail": "Pipelines typically include linting, unit/integration tests, security scans, artifact builds and staged deployments with rollback.",
    },
    "authentication": {
        "aliases": ["auth", "login", "oauth", "sso"],
        "definition": "Authentication is checking who someone is, for example by password or a sign-in provider.",
        "example": "Signing in with your Google account to use an app.",
        "analogy": "Like showing your ID card at a building entrance.",
        "steps": ["User provides credentials.", "The system verifies them.", "A session or token proves identity for later requests."],
        "detail": "Authentication (who you are) differs from authorization (what you may do); OAuth 2.0/OIDC and MFA are common standards.",
    },
    "scalability": {
        "aliases": ["scale", "scaling", "scalable"],
        "definition": "Scalability is a system's ability to handle more users or data by adding resources.",
        "example": "A scalable app keeps working smoothly when users grow from 1,000 to 100,000.",
        "analogy": "Like a restaurant that can add tables and cooks when more guests arrive.",
        "steps": ["Measure where the system slows down.", "Scale up (bigger machine) or out (more machines).", "Remove bottlenecks such as a single database."],
        "detail": "Horizontal scaling requires stateless services, partitioning/sharding and attention to coordination costs.",
    },
    "mvp": {
        "aliases": ["minimum viable product"],
        "definition": "An MVP is the simplest version of a product that is useful enough to test with real users.",
        "example": "A first version of a food app that only supports ordering from three restaurants.",
        "analogy": "Like a skateboard before a car: basic, but it already gets you somewhere.",
        "steps": ["Pick the core problem.", "Build only what is needed to solve it.", "Release to users and learn.", "Improve based on feedback."],
        "detail": "MVPs are about validated learning; scope is cut aggressively while keeping quality acceptable for the tested use case.",
    },
}


def lookup(term: str) -> tuple[str, dict] | tuple[None, None]:
    t = term.strip().lower().strip("\"'“”.,?!")
    if t in GLOSSARY:
        return t, GLOSSARY[t]
    for key, entry in GLOSSARY.items():
        if t in entry.get("aliases", []):  # type: ignore[operator]
            return key, entry
    for key, entry in GLOSSARY.items():
        names = [key, *entry.get("aliases", [])]  # type: ignore[misc]
        if any(len(n) > 2 and (f" {n} " in f" {t} ") for n in names):
            return key, entry
    return None, None


def terms_in(text: str) -> list[str]:
    low = f" {text.lower()} "
    found = []
    for key, entry in GLOSSARY.items():
        names = [key, *entry.get("aliases", [])]  # type: ignore[misc]
        if any(f" {n} " in low or f" {n}," in low or f" {n}." in low or f" {n}?" in low for n in names if len(n) > 2):
            found.append(key)
    return found
