CREATE TABLE IF NOT EXISTS opportunities (
    id           SERIAL PRIMARY KEY,
    name         TEXT    NOT NULL,
    region       TEXT    NOT NULL,
    customer_id  TEXT    NOT NULL,
    amount_usd   NUMERIC(12, 2) NOT NULL,
    stage        TEXT    NOT NULL,
    closes_on    DATE
);

CREATE INDEX IF NOT EXISTS opportunities_region_idx ON opportunities(region);
CREATE INDEX IF NOT EXISTS opportunities_customer_idx ON opportunities(customer_id);

INSERT INTO opportunities (name, region, customer_id, amount_usd, stage, closes_on) VALUES
    ('Acme - Q3 expansion',     'EMEA', 'acme',    240000, 'negotiation', '2026-06-30'),
    ('Acme - support uplift',   'EMEA', 'acme',     45000, 'closed-won',   '2026-04-12'),
    ('Globex - data uplift',    'AMER', 'globex',   90000, 'discovery',   '2026-08-15'),
    ('Globex - integrations',   'AMER', 'globex',  120000, 'proposal',    '2026-07-10'),
    ('Initech - pilot',         'AMER', 'initech',  18000, 'closed-lost', '2026-02-28'),
    ('Initech - renewal',       'AMER', 'initech',  36000, 'negotiation', '2026-09-01'),
    ('Acme - APAC pilot',       'APAC', 'acme',     60000, 'discovery',   '2026-09-30'),
    ('Globex - APAC kickoff',   'APAC', 'globex',  150000, 'proposal',    '2026-10-20')
ON CONFLICT DO NOTHING;
