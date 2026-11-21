# Local security setup

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env` and set unique local `JWT_SECRET` and `PASSWORD_PEPPER` values.
3. Set `DATABASE_URL` to a local SQLite URL or your PostgreSQL connection URL.
4. Run the API with `python -m uvicorn main:app --reload --port 8000`.
5. Run tests from this directory with `python -m pytest`.

For Vercel, set `DATABASE_URL`, `JWT_SECRET`, and `PASSWORD_PEPPER` as encrypted Environment Variables for Production, Preview, and Development as appropriate. Use independently generated random values of at least 32 bytes for both secrets. Never commit real secrets or paste them into source control.

The first administrator must be promoted through a trusted database administration session after signup. Public signup always creates a normal `user` account.
