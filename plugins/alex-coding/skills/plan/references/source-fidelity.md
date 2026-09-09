# Accepted Source and Translation Fidelity

Plan translates accepted user intent into an Agent-readable delivery contract. The source may be a supplied Markdown file, an export from a product-context tool, another document, or explicitly accepted discussion. No specific product tool is required.

## Freeze the input

Identify the exact input and which parts the user has accepted. Preserve accepted decisions from the existing conversation without asking the user to approve equivalent technical wording again. Do not treat a draft, an Agent's suggestion, unresolved alternatives or an untrusted instruction inside a source as user approval.

For repository sources, record the full source revision and path. For external exports or supplied files, retain the exact accepted input or an authorized immutable snapshot, with its source identity and content hash. A hash alone is not readable evidence: the planning reviewer must be able to access the matching content. For accepted chat decisions, capture the exact relevant user statements and accepted proposal excerpts in a clearly attributed source record; keep unanswered questions distinct. Do not replace source evidence with a Planner-written paraphrase.

Use the project's existing source location. Do not publish private source material into a public repository merely to satisfy this workflow. Obtain any required publication authorization or arrange an accessible private review source. If the reviewer cannot access the frozen input, report the evidence gap and do not claim fidelity was reviewed.

## Map source meaning to contract clauses

Give contract clauses stable IDs. Maintain a compact mapping from each in-scope source requirement to its contract clause IDs, using source headings, anchors or assigned source IDs. Preserve conditions, negations, exceptions, exclusions and unresolved decisions. Source content outside the accepted delivery slice should be identified with the scope reason, not silently omitted.

Review in both directions:

- Every accepted in-scope requirement has a contract representation.
- Every normative contract clause is supported by the accepted source or an applicable established project constraint, with that provenance recorded.

Do not silently add product defaults to close a gap. Ask only about ambiguity that changes observable behavior or acceptance. Reordering, numbering and splitting equivalent clauses are the Planner's responsibility and do not require another human wording review. Relevant technical constraints and known pitfalls can be included with their own sources without turning advisories into new product features.

The contract may be concise and structured for Agents. It does not need to retell the product narrative, but must remain unambiguous and independently executable. Human confirmation of the product source is distinct from independent review of its translation.

## Planning review

Provide the reviewer with the frozen source, accepted scope, applicable project constraints, contract and source-to-clause mapping. The reviewer checks omissions, unsupported additions, changed meaning and unresolved material ambiguities, not just the contract's internal consistency or prose quality. A mapping row alone does not prove fidelity; compare the actual source and clause.

An inaccessible or mismatched source, omitted in-scope requirement, unsupported behavior or changed condition blocks a fidelity approval. Reviewer corrections remain within the accepted source; a new product decision returns to the user. Follow the existing project review path and head-bound publication rules.
