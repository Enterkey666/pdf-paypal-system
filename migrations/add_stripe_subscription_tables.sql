-- Stripe Subscription Tables Migration
-- 実行日: 2025-07-28
-- 目的: Stripe決済統合のためのテーブル追加

-- users テーブルに stripe_customer_id 列を追加
ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;
ALTER TABLE users ADD COLUMN google_sub TEXT UNIQUE;

-- subscriptions テーブル作成
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    stripe_subscription_id TEXT UNIQUE NOT NULL,
    plan_id TEXT NOT NULL, -- 'Pro'
    status TEXT NOT NULL, -- 'active', 'trialing', 'past_due', 'canceled', 'unpaid'
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    cancel_at_period_end BOOLEAN DEFAULT 0,
    trial_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- entitlements テーブル作成
CREATE TABLE IF NOT EXISTS entitlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    feature TEXT NOT NULL, -- 'ocr_google', 'ocr_azure'
    limit_value TEXT DEFAULT 'ON', -- 'ON', 'OFF', または数値
    reset_period TEXT DEFAULT 'monthly', -- 'monthly', 'daily', 'none'
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    UNIQUE(user_id, feature)
);

-- webhook_events テーブル（冪等性キー管理用）
CREATE TABLE IF NOT EXISTS webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stripe_event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_result TEXT
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_id ON subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_entitlements_user_feature ON entitlements(user_id, feature);
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub);

-- 既存ユーザーに初期エンタイトルメントを付与（有料会員のみ）
INSERT OR IGNORE INTO entitlements (user_id, feature, limit_value)
SELECT u.id, 'ocr_google', 'ON'
FROM users u
WHERE u.id NOT IN (SELECT user_id FROM entitlements WHERE feature = 'ocr_google');

INSERT OR IGNORE INTO entitlements (user_id, feature, limit_value)
SELECT u.id, 'ocr_azure', 'ON'
FROM users u
WHERE u.id NOT IN (SELECT user_id FROM entitlements WHERE feature = 'ocr_azure');