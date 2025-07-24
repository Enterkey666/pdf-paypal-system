# Stripe機能テストガイド

## 📋 概要

このドキュメントは、Stripe決済機能追加後のテストケースと検証方法について説明します。

## 🏗️ テスト構成

### 自動テストスイート

```
tests/
├── __init__.py                     # テストモジュール初期化
├── test_stripe_integration.py     # Stripe統合テスト
├── test_performance.py            # パフォーマンステスト
├── test_security.py               # セキュリティテスト
├── test_integration.py            # システム統合テスト
└── test_runner.py                 # テストランナー
```

### 手動テスト

- `MANUAL_TEST_PROCEDURES.md` - 詳細な手動テスト手順書

## 🚀 クイックスタート

### 1. テスト環境準備

```bash
# テスト用依存関係のインストール
pip install -r requirements-test.txt

# 環境変数設定
export STRIPE_SECRET_KEY_TEST=sk_test_your_key
export STRIPE_PUBLISHABLE_KEY_TEST=pk_test_your_key
export STRIPE_MODE=test
```

### 2. スモークテスト実行

```bash
# 基本機能の動作確認（1分以内）
python tests/test_runner.py --mode smoke
```

### 3. フルテスト実行

```bash
# 全テスト実行（カバレッジ付き）
python tests/test_runner.py --mode full

# 高速テスト（重いテストを除外）
python tests/test_runner.py --mode quick --no-coverage
```

## 🧪 テストケース詳細

### 1. Stripe API接続テスト

**対象**: `test_stripe_integration.py::TestStripeAPIConnection`

```bash
# 個別実行
pytest tests/test_stripe_integration.py::TestStripeAPIConnection -v
```

**テスト内容**:
- ✅ 正常なStripe接続
- ✅ 無効なAPIキーの処理
- ✅ Stripe設定の検証
- ✅ APIエラーハンドリング

### 2. 決済リンク生成テスト

**対象**: `test_stripe_integration.py::TestStripePaymentLinkGeneration`

```bash
# 決済リンクテスト実行
pytest tests/test_stripe_integration.py::TestStripePaymentLinkGeneration -v
```

**テスト内容**:
- ✅ 基本的な決済リンク作成
- ✅ 通貨変換処理（JPY, USD, EUR）
- ✅ 無効金額の処理
- ✅ 長い顧客名の処理

### 3. OCR統合テスト

**対象**: `test_stripe_integration.py::TestOCRIntegration`

```bash
# OCR統合テスト実行
pytest tests/test_stripe_integration.py::TestOCRIntegration -v
```

**テスト内容**:
- ✅ OCRデータ抽出・検証
- ✅ OCRからStripe決済リンク作成
- ✅ 日本語データ処理
- ✅ 無効データの処理

### 4. プロバイダー切り替えテスト

**対象**: `test_stripe_integration.py::TestProviderSwitching`

```bash
# プロバイダー切り替えテスト
pytest tests/test_stripe_integration.py::TestProviderSwitching -v
```

**テスト内容**:
- ✅ PayPal ⇔ Stripe切り替え
- ✅ 無効プロバイダーの処理
- ✅ 設定による動作変更

### 5. エラーハンドリングテスト

**対象**: `test_stripe_integration.py::TestErrorHandling`

```bash
# エラーハンドリングテスト
pytest tests/test_stripe_integration.py::TestErrorHandling -v
```

**テスト内容**:
- ✅ Stripe APIエラー
- ✅ ネットワークタイムアウト
- ✅ レート制限処理

### 6. 日本語対応テスト

**対象**: `test_stripe_integration.py::TestJapaneseLanguageSupport`

```bash
# 日本語対応テスト
pytest tests/test_stripe_integration.py::TestJapaneseLanguageSupport -v
```

**テスト内容**:
- ✅ 日本語文字処理
- ✅ 特殊文字処理（㈱、全角数字）
- ✅ エンコーディング確認

## ⚡ パフォーマンステスト

### 実行方法

```bash
# 軽量パフォーマンステスト
pytest tests/test_performance.py -m "not slow" -v

# 全パフォーマンステスト（時間要）
pytest tests/test_performance.py --include-slow -v
```

### 測定項目

| 項目 | 基準値 | 測定内容 |
|------|--------|----------|
| 単一決済リンク作成 | <1秒 | 基本処理時間 |
| 連続10リクエスト | 平均<500ms | 処理安定性 |
| 並行5リクエスト | 効率>0.5 | 並行処理効果 |
| 大量データ処理 | <3秒 | スケーラビリティ |
| メモリ使用量 | 増加<50MB | メモリリーク確認 |

### パフォーマンス基準

```python
# 基準値定義（test_performance.py内）
PERFORMANCE_BENCHMARKS = {
    'single_request_max_time': 1.0,     # 秒
    'average_request_max_time': 0.5,    # 秒
    'concurrent_efficiency_min': 0.5,   # 効率
    'large_data_max_time': 3.0,         # 秒
    'memory_increase_max': 50.0         # MB
}
```

## 🔒 セキュリティテスト

### 実行方法

```bash
# セキュリティテスト実行
pytest tests/test_security.py -v
```

### テスト項目

#### APIキーセキュリティ
- ✅ APIキー暗号化・復号化
- ✅ ログへのAPIキー漏洩防止
- ✅ エラーメッセージのサニタイゼーション
- ✅ 暗号化キーファイル権限

#### 設定セキュリティ
- ✅ エクスポート時の機密データ除外
- ✅ インジェクション攻撃防止
- ✅ 安全な設定インポート

#### 入力検証
- ✅ 金額入力検証
- ✅ 顧客名サニタイゼーション
- ✅ ファイルアップロード検証

#### Webhookセキュリティ
- ✅ 署名検証
- ✅ ペイロード検証
- ✅ 不正形式データ処理

## 🔧 統合テスト

### 実行方法

```bash
# 統合テスト実行
pytest tests/test_integration.py -v
```

### テストカテゴリ

#### フルワークフロー
- ✅ PDF→OCR→Stripe決済の完全フロー
- ✅ プロバイダーフェイルオーバー
- ✅ 設定永続化
- ✅ エラー回復

#### 並行動作
- ✅ 並行決済リンク作成
- ✅ 並行設定アクセス

#### データ永続化
- ✅ 決済履歴統合
- ✅ 設定バックアップ・復元

#### システム復旧力
- ✅ 部分的サービス障害
- ✅ データベース接続失敗
- ✅ ファイルシステム問題

## 📊 テストレポート

### 自動レポート生成

```bash
# HTMLレポート付きで実行
python tests/test_runner.py --mode full

# 生成されるファイル:
# test_reports/test_report_YYYYMMDD_HHMMSS.html
# test_reports/test_report_YYYYMMDD_HHMMSS.json
```

### レポート内容

- **サマリー**: 成功率、実行時間、統計
- **テストスイート詳細**: 各カテゴリの結果
- **カバレッジレポート**: コードカバレッジ
- **推奨アクション**: 問題がある場合の対応策

### サンプルレポート

```
📊 テスト結果サマリー
┌─────────────┬─────┬─────┬─────────┬──────────┐
│             │成功 │失敗 │スキップ │ 成功率   │
├─────────────┼─────┼─────┼─────────┼──────────┤
│ 統合テスト  │ 25  │  0  │   1     │ 100.0%   │
│ 性能テスト  │ 15  │  1  │   2     │  93.8%   │
│ 安全テスト  │ 20  │  0  │   0     │ 100.0%   │
│ 総合テスト  │ 12  │  0  │   1     │ 100.0%   │
└─────────────┴─────┴─────┴─────────┴──────────┘
```

## 🎯 手動テスト

### 基本操作テスト

1. **設定画面テスト**
   ```
   1. /settings にアクセス
   2. Stripe設定を入力
   3. 接続テスト実行
   4. 包括テスト実行
   ```

2. **PDF処理テスト**
   ```
   1. メイン画面でPDFアップロード
   2. OCR処理確認
   3. Stripe選択
   4. 決済リンク作成
   ```

### 境界値テスト

| 項目 | 最小値 | 最大値 | 期待結果 |
|------|--------|--------|----------|
| 金額 | ¥1 | ¥99,999,999 | 正常処理 |
| 顧客名 | 1文字 | 500文字 | 正常処理 |
| 説明 | 空 | 1000文字 | 正常処理 |

### エラーシナリオテスト

```bash
# 無効APIキーテスト
export STRIPE_SECRET_KEY_TEST=sk_test_invalid
# → "認証エラー"が表示される

# ネットワークエラーテスト
# ネットワーク切断状態で決済リンク作成
# → "接続エラー"が表示される

# 不正入力テスト
# 金額: -1000, 顧客名: <script>alert(1)</script>
# → 適切にサニタイズされる
```

## 🐛 トラブルシューティング

### よくある問題

#### 1. テスト失敗: "Stripe library not found"

**原因**: Stripeライブラリ未インストール

**解決方法**:
```bash
pip install stripe==7.0.0
```

#### 2. テスト失敗: "Invalid API key"

**原因**: 環境変数の設定不備

**解決方法**:
```bash
# .envファイル確認
cat .env | grep STRIPE

# 正しい形式か確認
# STRIPE_SECRET_KEY_TEST=sk_test_xxxx
# STRIPE_PUBLISHABLE_KEY_TEST=pk_test_xxxx
```

#### 3. パフォーマンステスト失敗

**原因**: システムリソース不足

**解決方法**:
```bash
# 軽量テストで実行
pytest tests/test_performance.py -m "not slow"

# 並行数を調整
# test_performance.py内のconcurrent_countを減らす
```

#### 4. 日本語文字化け

**原因**: エンコーディング設定

**解決方法**:
```bash
# 環境変数設定
export LANG=ja_JP.UTF-8
export LC_ALL=ja_JP.UTF-8

# Pythonエンコーディング確認
python -c "import sys; print(sys.getdefaultencoding())"
```

### ログ確認方法

```bash
# アプリケーションログ
tail -f logs/app.log

# テスト実行ログ
pytest tests/ -v --capture=no

# デバッグモード実行
export DEBUG=True
python tests/test_runner.py --mode smoke
```

### デバッグ実行

```bash
# 詳細出力でテスト実行
pytest tests/test_stripe_integration.py -v -s --tb=long

# 特定テストのみデバッグ実行
pytest tests/test_stripe_integration.py::TestStripeAPIConnection::test_valid_stripe_connection -v -s --pdb
```

## 📋 チェックリスト

### リリース前チェック

- [ ] 全自動テストが成功（成功率95%以上）
- [ ] 手動テストの基本シナリオが全て成功
- [ ] パフォーマンステストが基準値をクリア
- [ ] セキュリティテストが全て成功
- [ ] 本番環境でのスモークテストが成功
- [ ] ログに機密情報が含まれていない
- [ ] エラーメッセージが適切にサニタイズされている

### 運用開始後チェック

- [ ] 決済成功率の監視
- [ ] 応答時間の監視
- [ ] エラー率の監視
- [ ] Webhookの動作確認
- [ ] ログ出力の確認

## 🚀 継続的インテグレーション

### GitHub Actions設定例

```yaml
# .github/workflows/stripe-tests.yml
name: Stripe Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    - name: Run tests
      env:
        STRIPE_SECRET_KEY_TEST: ${{ secrets.STRIPE_SECRET_KEY_TEST }}
        STRIPE_PUBLISHABLE_KEY_TEST: ${{ secrets.STRIPE_PUBLISHABLE_KEY_TEST }}
      run: |
        python tests/test_runner.py --mode quick --no-coverage
```

### ローカルでの継続実行

```bash
# ファイル変更時の自動テスト実行
pip install pytest-watch
ptw tests/ -- --tb=short
```

## 📈 テスト品質向上

### カバレッジ向上

```bash
# 現在のカバレッジ確認
pytest tests/ --cov=. --cov-report=html
# htmlcov/index.html で詳細確認

# 未カバー行の確認
pytest tests/ --cov=. --cov-report=term-missing
```

### テストケース追加

新機能追加時は以下の観点でテストケースを追加:

1. **正常系**: 基本的な動作確認
2. **異常系**: エラー処理の確認
3. **境界値**: 最小/最大値での動作確認
4. **セキュリティ**: 攻撃パターンへの対応確認
5. **パフォーマンス**: 性能要件の確認

---

## 📞 サポート

テストに関する質問や問題が発生した場合:

1. **ドキュメント確認**: 本ガイドとコメント
2. **ログ確認**: エラーログの詳細分析
3. **環境確認**: 依存関係とバージョン
4. **再現手順**: 最小限の再現手順を作成

---

*このテストガイドはStripe機能の品質保証と安定運用を目的として作成されています。定期的な更新と改善を推奨します。*