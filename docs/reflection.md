# Reflection

I drew the tool boundaries around three different intentions. `search_catalog`
answers a question without changing stored state, while `reserve_book` performs
one persistent reservation for an explicit book and student. Validation and
availability checks belong inside the reservation operation because a caller
must not be able to bypass them. `reserve_matching_book` represents the higher-level
intention of reserving a suitable book by topic. It calls the same search and
reservation implementations used by the individual MCP tools, so coordination
does not duplicate their rules. The apparent tension between a single-purpose
tool and a multi-step workflow is resolved by defining purpose at the user's
level: the workflow has one outcome, even though achieving it requires two kinds
of operation. Explicit errors, deterministic ordering, and idempotent reservations
make those boundaries observable and predictable.

Three tools felt appropriate for this deliberately small use case: they let the
agent demonstrate information retrieval, a real state change, and coordination
without a large menu of overlapping functions. The constraint would become
restrictive for a complete library service, where cancellation, account lookup,
and loan renewal each deserve their own contracts. A practical challenge was
ensuring that search remained read-only while still reporting current reservation
availability. Separating read-only database access from lazy initialization on
the action path addressed this. Transactions protect the check-and-reserve step,
and duplicate requests return the existing receipt. Next steps would include
authenticated student accounts, reservation expiry, an actual library catalog
adapter, and broader evaluations of the model's routing decisions. Gemini keeps
the model provider separate from the required OpenAI Agents SDK host, but free-tier
availability and rate limits remain external constraints that the application
must report clearly.
