CREATE INDEX idempotency_responses_by_state_created
ON idempotency_responses(state, created_at);

CREATE INDEX checkpoint_publications_by_state_published
ON checkpoint_publications(state, published_at);
