# Selected REST read contract

**Maintainer decision: EF-V5-ENGINE-READ-CONTRACT-P1 revision 2, 2026-10-11.**
Both unchecked get-by-ID binding and ignored collection selectors must be fixed
before v5. This is support-or-refuse, not D10, a query engine, authorization or
release acceptance. Earlier observations remain in the
[external-review backlog](external-review-backlog.md#xr-1-adjacent-operation-audit).

## Supported And Refused Reads

| Selected contract | Behavior |
| --- | --- |
| Own persistence-ID read | One typed path input, independently selected entity identity, and that entity's own collection immediately before the ID. Get-by-ID accepts the ID field's case-insensitive spelling or generic `id`; names alone are insufficient. |
| Foreign-resource ID, business key, additional nested selector | Refuse, never pass the last path value to `findById`. |
| Unfiltered collection | Support without ignored record selectors, including compatible static list subroutes on read-only and mixed CRUD surfaces. Multiple distinct primary get/list contracts on mixed CRUD are refused rather than silently choosing one. |
| Existing `pageable: true` | Preserve Engine `page`/`size` pagination: defaults 0/20, maximum size 200 and offset 50,000. Arbitrary declared query filters, including `pageSize`, are not implemented. |
| Computed ID read | Retain XR-1's exact ID-name/type and `/<snake_case_entity>s/{<id_field>}` layout with optional static prefix/suffix and mapped response fields. |
| Declared query/cookie/body selection or unclassified custom header | Refuse. Header classification cannot exempt another location. |
| Unpreservable route, missing variables, patterns/matrix syntax or colliding scoped reads | Refuse before output mutation; do not emit a plausible alternate route. General route hardening outside these reads stays separate. |

Original GET metadata is checked alongside dispatch categories, before selected
context deduplication. Changing an operation name cannot exempt an unsupported
contract. Generation, planning and apply report the operation, interface, entity
and unsupported input before mutating output, including developer files. Only
selected operations are checked, not unrelated unselected operations in a spec.
Selected GETs bind to their returned canonical entity for both preflight and
emission, even when an unmapped request sample associates their request with a
fieldless placeholder. Such a sample cannot exempt an owner-key lookup, body or
other unsupported selector. A sample alone does not declare a request body;
otherwise-supported reads remain usable. Missing or fieldless selected returned
entities are refused before output mutation.

Identity inference must select the same unambiguous field without GET routes or
GET request mappings; otherwise use the existing `identity_overrides.persistence_id`.
An accepted path-ID mapping names that exact input in the selected operation's
request context. Transport context is the prefix for the selected interface and
operation, not a matching token anywhere in a field path. A response property
named `request` is still response data; a request property named `response` is
still an input. Malformed or wrong-context mappings remain visible to refusal
checks instead of being discarded. Nested/ambiguous source paths are not reduced
to their final token; a dotted header name cannot masquerade as the path ID.
This does not replace global identity inference. Canonical metadata retains a
failed independent identity check through serialization. The shipped
wire-transfer sample explicitly declares its existing `InternationalPaymentId`
key to resolve duplicate casing without changing that selection or Manifest 2.0.
Its `/international-payments/{InternationalPaymentId}` GET remains supported.
Static route segments such as `me` do not impose ownership or record scope;
accepted own-ID routes still require adopter-owned object/tenant authorization.
Sample-only inputs without a declared REST route/selector retain the existing
Engine generic CRUD surface; a request-sample selector is not promoted to a lookup.

## Explicit Header Classification

Declare `x-edgeforge-read-input-role` on an ordinary OpenAPI **Parameter Object**:

```yaml
components:
  parameters:
    RequestTrace:
      name: X-Correlation-Id
      in: header
      required: false
      schema:
        type: string
      x-edgeforge-read-input-role: metadata
```

- `metadata`: does not select, filter, scope or authorize records.
- `gateway-rate-limit`: external rate-limit context, not record selection or authentication.

Canonical `operation_parameters[].read_input_role` retains this contract-author
declaration. It is not proof of arbitrary business semantics. Contradictory
security-scheme usage (including active local references) or raw canonical record
request mapping is refused before mapping deduplication, as are
unknown roles and classifications on query/cookie/path inputs. There is no
header-name allowlist or description inference. Only declared inputs are checked,
not incidental client headers.

Classified headers also require a compilable Java binding: HTTP-token validity,
distinct argument names, and no keyword/generated-local/member collisions.
Unsupported bindings are refused early, not renamed into an undocumented contract.
Computed reads use the same classified-header rule during preflight and rendering.

Header handling is case-insensitive. OpenAPI's special header Parameter rule
ignores `Authorization`, `Accept` and `Content-Type` declarations as parameters.
Source security requirements/schemes and media-type declarations remain intact.
This does not generate authentication or waive those declarations. Deployment
still requires the established authenticated gateway and protected application ports.

Local-document JSON pointers are resolved before validation, including component
Parameter Objects and bounded reference chains. Malformed, missing, cyclic,
external or excessively deep references retain errors for selected-read preflight,
rather than erasing inputs. No remote reference is fetched or path outside the
input package loaded. Put the extension on the actual target Parameter Object,
not beside an OpenAPI 3.0 `$ref`.

The shipped sample's four request/correlation headers are `metadata`;
`x-client-id` is `gateway-rate-limit`, consistent with its existing prohibition
on authentication use. Other business headers are not classified by analogy.
Classification implements neither correlation echo, rate limiting,
authentication, object/tenant authorization nor adopter business logic.
Those remain external or separately scoped. No Studio UI or manifest version changes.
Generated console read descriptors use the same selected routes as controllers,
including static list subroutes on mixed CRUD. This is not browser-journey proof.

## Proof Boundary

Focused tests cover both P1s, name/dispatch changes, inline/referenced roles,
special headers, invalid refs/selectors, route fidelity, selected-operation scope
and output preservation. `python -m scripts.smoke.read_contract_proof` reuses the
existing Maven/PostgreSQL/independence helpers with synthetic test metadata and
three active-profile cases. It requires explicit output/JDK paths and the existing
loopback PostgreSQL proof environment. This is not Suite L5 or a security audit.
See the [dated proof record](test-results/read-contract-p1-2026-10-11.md).
