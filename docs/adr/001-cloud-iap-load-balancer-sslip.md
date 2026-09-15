# ADR 001: Cloud IAP Zero-Trust Access, Global HTTPS Load Balancer & Dynamic sslip.io Wildcard DNS

## Status
**ACCEPTED & IMPLEMENTED** (2026-09-15)

## Context & Problem Statement
MindTheSpot is deployed as a containerized service on Google Cloud Run (`mindthespot-app`) in region `europe-west4` within GCP project `jcf-mindthespot`.

When accessing the direct Cloud Run endpoint (`https://mindthespot-app-lodn3fqcaa-ez.a.run.app/`), users encountered:
`Error: Forbidden - Your client does not have permission to get URL / from this server.`

Furthermore, attempts to grant public access (`allUsers` or `allAuthenticatedUsers`) with `roles/run.invoker` were blocked by the organization's **Domain Restricted Sharing (DRS)** constraint:
```
FAILED_PRECONDITION: One or more users named in the policy do not belong to a permitted customer,
perhaps due to an organization policy (constraints/iam.allowedPolicyMemberDomains).
```

### Constraints & Requirements
1. **Zero-Trust Access Control:** Only authenticated organizational users (e.g. `*.altostrat.com` domains) may access the MindTheSpot FinOps dashboard and APIs.
2. **Organizational DRS Compliance:** No public `allUsers` IAM bindings may exist.
3. **Automated SSL & Domain Provisioning:** The deployment must not require external manual DNS zone delegation or registrar API keys.
4. **GitOps Automation:** All infrastructure must be managed declaratively via Terraform within GitHub Actions using Workload Identity Federation (WIF).

---

## Decision

We designed and implemented a production-grade edge architecture combining:

1. **Global External Application Load Balancer (`EXTERNAL_MANAGED`):**
   - Provisions a dedicated Global Anycast IPv4 address (`8.232.252.55`).
   - Routes ingress traffic across Google's global fiber network.
   - Forwards port 80 (HTTP) to port 443 (HTTPS) with a permanent 301 redirect.

2. **Serverless Network Endpoint Group (NEG):**
   - Bridges the Global Load Balancer to the regional Cloud Run service in `europe-west4`.
   - Bypasses public internet routing via Google Front End (GFE) internal interconnects.

3. **Cloud Identity-Aware Proxy (IAP):**
   - Attached to the Load Balancer Backend Service (`mindthespot-backend-service`).
   - Uses an OAuth 2.0 Web Application client credentials pair (`IAP_CLIENT_ID` / `IAP_CLIENT_SECRET`).
   - Enforces zero-trust browser authentication via Google Cloud Identity / Google Workspace.
   - Authorizes users via IAM role `roles/iap.httpsResourceAccessor` assigned to `domain:jcfesantieu.altostrat.com` and `user:sre@jcfesantieu.altostrat.com`.
   - Propagates user identity downstream via signed headers:
     - `X-Goog-Authenticated-User-Email`
     - `X-Goog-Authenticated-User-Id`
     - `X-Goog-IAP-JWT-Assertion`

4. **Private Cloud Run Perimeter & Service Agent Delegation:**
   - Cloud Run ingress is locked to `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` (Internal + Allow external Load Balancers). Direct internet calls to `*.run.app` are rejected with HTTP 403.
   - The Google Cloud IAP Service Agent (`serviceAccount:service-903096587182@gcp-sa-iap.iam.gserviceaccount.com`) is granted `roles/run.invoker` on the Cloud Run service.
   - When IAP authorizes a user at the edge, it signs an OIDC identity token for its own service agent and injects it into the `X-Serverless-Authorization` header. Cloud Run validates this header and allows the request.
   - Cloud Run configures `custom_audiences` for the Load Balancer FQDN and OAuth Client ID.

5. **Dynamic FQDN with sslip.io & Google-Managed SSL:**
   - Uses `sslip.io` wildcard DNS resolution: the FQDN is calculated directly from the static external IP address:
     `spot-${replace(local.lb_ip, ".", "-")}.sslip.io` $\rightarrow$ `https://spot-8-232-252-55.sslip.io`
   - Terraform automatically creates a `google_compute_managed_ssl_certificate` targeting this FQDN.
   - Google CA issues and maintains the SSL certificate automatically with zero manual DNS validation steps.

---

## Implementation Details & Gotchas Resolved

1. **Serverless NEG Backend Service Parameters:**
   - *Issue:* Google Compute Engine rejects `timeout_sec` and `port_name` on backend services backed by Serverless NEGs with `Error 400: Timeout sec is not supported for a backend service with Serverless network endpoint groups.`
   - *Resolution:* Removed `timeout_sec` and `port_name` from `google_compute_backend_service.app_backend`.

2. **OAuth 2.0 Redirect URI Formatting:**
   - *Issue:* Visiting the protected domain triggered `Error 400: redirect_uri_mismatch`.
   - *Resolution:* Cloud IAP requires the exact redirect URI format in the OAuth Client:
     `https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect`

3. **GitOps Integration with Secret Injection:**
   - *Workflow:* `.github/workflows/gitops.yml` reads `IAP_CLIENT_ID` and `IAP_CLIENT_SECRET` from GitHub repository secrets.
   - When present, it automatically activates `enable_iap=true` and supplies credentials to `terraform apply`.

---

## Consequences & Benefits

### Positive
- **No Organization Policy Conflicts:** Complies 100% with `constraints/iam.allowedPolicyMemberDomains` since Cloud Run requires no public `allUsers` role.
- **Enterprise-Grade Identity:** FinOps and DevOps teams authenticate with corporate Google Workspace accounts without requiring application-level auth code.
- **Edge Security:** Requests are screened at Google's global edge before consuming Cloud Run compute resources.
- **Automated Zero-Touch DNS/SSL:** `sslip.io` provides immediate valid TLS without registering custom DNS zones.
