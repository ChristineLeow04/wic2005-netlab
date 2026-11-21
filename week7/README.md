
# WIC2005 Week 7 — Make the API Match Your Intent

## Overview

This project automates the configuration of VLANs and Access Control List (ACL) entries through a REST API.

The desired configuration is defined in `intent.yaml`. The Python client, `sync.py`, compares the desired configuration with the API's existing state, calculates the required changes, applies them safely, and verifies the final result.

Student ID suffix: 4965

Network address block: 10.65.0.0/16

## 1. Network Design

My intended network represents a small university data centre.

### VLAN Configuration

| VLAN ID | Name |
|---|---|
| 10 | students |
| 20 | servers |
| 30 | guests |
| 40 | lecturers |
| 50 | admin |
| 60 | research |

VLAN 1 belongs to the API and is preserved during synchronization.

### ACL Configuration

Five ACL entries are defined to control network access:

1. Deny SSH access from guests to servers.
2. Permit HTTPS access from students to servers.
3. Permit SSH access from lecturers to servers.
4. Deny RDP access from guests to the administration network.
5. Permit HTTPS access from the research network to servers.

All ACL addresses belong to the 10.65.0.0/16 address block.

## 2. How sync.py Decides What to Change

The program first loads `intent.yaml` using PyYAML. It then connects to the API, authenticates using environment variables, and retrieves the existing VLAN and ACL configurations.

The `build_plan()` function compares the desired and actual states. For VLANs, it uses the VLAN ID to identify missing, existing and unwanted resources.

In my fresh API, VLAN 10 was named `users`, but my intended name was `students`. Therefore, the program planned a PUT operation to rename VLAN 10.

VLANs 30, 40, 50 and 60 were missing, so the program planned to create them. VLAN 99 was not included in my intent, so the program planned to delete it. VLAN 1 was preserved.

For ACL entries, the program compares the action, source, destination, protocol, port and description instead of the automatically assigned server ID. For example, the `guests-no-ssh` rule was missing, so the program planned to create it using POST.

The initial synchronization plan contained 11 changes: four VLAN creations, one VLAN update, one VLAN deletion and five ACL creations.

## 3. How Requests Are Safely Retried

My `safe_request()` function handles temporary API failures.

For HTTP 429, the program reads the `Retry-After` header and waits before trying again.

For HTTP 503, connection errors and timeouts, it uses exponential backoff with a small random delay.

For HTTP 401, the program authenticates again and retries the request with a fresh bearer token.

VLAN PUT operations are idempotent because repeating an update leaves the VLAN in the same intended state.

DELETE operations are also idempotent in their effect. If a repeated DELETE returns HTTP 404 because the resource is already absent, the program treats the deletion as complete.

ACL creation uses POST, which is not naturally idempotent. Therefore, the program uses an Idempotency-Key to protect each logical ACL creation.

Unexpected HTTP errors are not repeatedly retried. The program raises an exception instead.

## 4. Why ACL POST Requires an Idempotency-Key

Unlike VLANs, which can be created or updated using PUT, ACL entries are created using POST.

Repeating a POST without protection could create identical ACL entries, especially if the API applies a change but loses its response.

My program uses `uuid.uuid4()` to generate a unique Idempotency-Key before creating an ACL entry. The same key is passed to every retry of that particular operation.

If the API receives the same key and request body again, it returns the earlier result rather than creating another entry.

Generating a new key for every retry would defeat this protection because the server would treat each attempt as a different operation.

Reusing the same key for unrelated operations or different request bodies would also be incorrect. The API rejects reuse of the same key with a different body using HTTP 422.

Each new planned ACL creation receives its own key. Before a new synchronization run applies changes, it reads the current state again, so ACL rules that already exist do not need to be recreated.

## 5. What If Two Users Run sync.py Simultaneously?

If two administrators execute `sync.py` at the same time with different intent files, they could interfere with each other's changes.

For example, one administrator might rename VLAN 10 to `students`, while another wants to rename it to `employees`. Both programs could read the original configuration and then apply conflicting updates.

The final configuration would depend on which update is processed last.

To prevent this, the API could support configuration version numbers, conditional requests using ETags and If-Match, or a locking mechanism that prevents simultaneous conflicting updates.

A centralized controller could also coordinate changes so that administrators do not overwrite each other's configurations.

## 6. Credential Management and Security

The script reads the API address from `LAB_API_URL`, with `http://api:8000` as the default.

Authentication credentials are provided through the `LAB_USERNAME` and `LAB_PASSWORD` environment variables.

The program retrieves a bearer token dynamically instead of storing one in the Python source code or YAML configuration.

No authentication tokens or passwords are included in the files intended for the GitHub repository.

The repository contains source code, intended network configuration and experimental evidence only.

## 7. Experimental Evidence

### Dry Run

The initial dry run identified 11 required changes without applying any modifications.

The API audit confirmed zero writes.

Evidence: `evidence/dry-run.txt`

### Apply Under Chaos

I enabled 30% response loss and 20% HTTP 503 errors.

Despite connection failures and temporary server errors, `sync.py` completed the synchronization successfully.

The final audit recorded 11 writes, matching the 11 planned operations. The API contained the six intended VLANs, VLAN 1, and five ACL entries.

Evidence: `evidence/apply.txt`

### Second Run

I ran the synchronization again without changing the intent.

The program reported zero planned changes and did not perform additional writes.

This demonstrated that the synchronization process is idempotent when the existing configuration already matches the intended state.

Evidence: `evidence/second-run.txt`

### Token Expiry

I restarted the API with a token lifetime of 3 seconds and a rate limit of 2 requests per second.

The program encountered expired authentication tokens and HTTP 429 responses. It successfully authenticated again, respected the rate limit and completed synchronization.

The final state matched the desired configuration.

Evidence: `evidence/expiry.txt`

## 8. Week 7 Lab — Key Findings

### Docker Networking

The `apilab` Docker network uses the bridge driver with subnet 172.18.0.0/16.

The API container was assigned 172.18.0.2, while the client container was assigned 172.18.0.3 during the lab.

Docker creates isolated network namespaces and connects the containers through virtual Ethernet interfaces and a Linux bridge. Its internal DNS allows the client to access the API using the hostname `api`.

### HTTP Status Codes

| Code | Meaning | Appropriate Client Action |
|---|---|---|
| 400 | Bad Request | Correct the malformed request |
| 401 | Unauthorized | Authenticate again |
| 403 | Forbidden | Obtain appropriate permissions |
| 404 | Not Found | Check the resource or URL |
| 405 | Method Not Allowed | Use a supported HTTP method |
| 409 | Conflict | Read the current state and resolve the conflict |
| 422 | Unprocessable Entity | Correct invalid data |
| 429 | Too Many Requests | Wait according to Retry-After |
| 503 | Service Unavailable | Retry safely with backoff |

Requests with permanent client errors should not be retried unchanged.

### Unsafe and Safe Retries

During the lab, `retry_naive.py` created duplicate ACL entries when the server applied a POST but lost its response.

The corrected `retry_safe.py` reused an Idempotency-Key for retries of the same operation.

Under 90% response-loss chaos, the safe script retried but the audit recorded only one new ACL entry.

### Inventory Client

My `inventory.py` successfully retrieved all 265 devices.

With 10 devices per page, the API required 27 successful page requests. The client sent 38 GET requests in total because it encountered temporary HTTP 503 errors and HTTP 429 rate limits.

The additional 11 requests were retries.

### OpenAPI Documentation

I discovered that the devices endpoint accepts a maximum limit of 50 per page and supports filtering by site.

The individual ACL endpoint supports GET and DELETE operations.

The OpenAPI documentation also revealed that reusing an Idempotency-Key with a different request body returns HTTP 422.

I successfully tested the site filter using `site=pj-dc`.

## 9. AI Use Declaration — Level 3 (Open)

I used ChatGPT (OpenAI) as a learning and development assistant for this assignment.

ChatGPT assisted with understanding REST API concepts, HTTP status codes, authentication, pagination, idempotency, retry mechanisms and synchronization logic.

It also helped me develop and debug Python functions, structure the experimental tests, interpret API responses and prepare technical explanations.

I executed the Docker containers and Python programs in my own environment, collected the experimental evidence, and verified the submitted results.

I reviewed the AI-assisted code and explanations and remain responsible for understanding and defending my work.

## 10. Running the Assignment

Set the required credentials in the client container environment.

Preview the synchronization plan without modifying the API:

`python3 sync.py intent.yaml --dry-run`

Apply the desired configuration and verify the result:

`python3 sync.py intent.yaml`

Running the script again against an already synchronized API should produce an empty plan and no additional writes.
