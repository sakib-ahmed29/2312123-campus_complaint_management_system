-- Add temporary account suspension support without changing existing account states.
ALTER TABLE public."user"
  ADD COLUMN IF NOT EXISTS suspended_until timestamptz,
  ADD COLUMN IF NOT EXISTS suspension_reason text;

CREATE INDEX IF NOT EXISTS ix_user_suspended_until
  ON public."user"(suspended_until)
  WHERE suspended_until IS NOT NULL;
