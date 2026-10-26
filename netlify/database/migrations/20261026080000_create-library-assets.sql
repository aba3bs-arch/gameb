CREATE TABLE library_assets (
  filename TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  bytes INTEGER NOT NULL CHECK (bytes > 0),
  type TEXT NOT NULL CHECK (type IN ('image/png', 'image/jpeg', 'image/webp')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
