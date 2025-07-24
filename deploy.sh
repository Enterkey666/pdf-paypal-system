#!/bin/bash

# ====================================
# PDF-PayPal-Stripe システム デプロイスクリプト
# ====================================

set -euo pipefail  # エラーで停止、未定義変数でエラー、パイプのエラーを伝播

# =============================
# 🎨 色定義
# =============================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# =============================
# 📝 ログ関数
# =============================
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# =============================
# 🔧 設定変数
# =============================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="pdf-paypal-stripe"
DOCKER_COMPOSE_FILE="docker-compose.yml"
BACKUP_DIR="./backups/deploy_backups"
LOG_FILE="./logs/deploy.log"

# デプロイモード（development, staging, production）
DEPLOY_MODE="${1:-staging}"

# =============================
# 📋 ヘルプ表示
# =============================
show_help() {
    echo -e "${CYAN}PDF-PayPal-Stripe システム デプロイスクリプト${NC}"
    echo ""
    echo "使用方法:"
    echo "  ./deploy.sh [MODE] [OPTIONS]"
    echo ""
    echo "MODE:"
    echo "  development  - 開発環境デプロイ"
    echo "  staging      - ステージング環境デプロイ（デフォルト）"
    echo "  production   - 本番環境デプロイ"
    echo ""
    echo "OPTIONS:"
    echo "  --help       - このヘルプを表示"
    echo "  --backup     - デプロイ前にバックアップを作成"
    echo "  --no-tests   - テストをスキップ"
    echo "  --force      - 確認プロンプトをスキップ"
    echo ""
    echo "例:"
    echo "  ./deploy.sh production --backup"
    echo "  ./deploy.sh development --no-tests"
}

# =============================
# 🛠️ 前提条件チェック
# =============================
check_prerequisites() {
    log_step "前提条件をチェック中..."
    
    # 必要なコマンドの存在確認
    local required_commands=("docker" "docker-compose" "git")
    
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "$cmd が見つかりません。インストールしてください。"
            exit 1
        fi
    done
    
    # Docker サービスの実行確認
    if ! docker info &> /dev/null; then
        log_error "Docker サービスが実行されていません。"
        exit 1
    fi
    
    # 必要なファイルの存在確認
    local required_files=(".env.example" "Dockerfile" "$DOCKER_COMPOSE_FILE")
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "必要なファイルが見つかりません: $file"
            exit 1
        fi
    done
    
    log_success "前提条件チェック完了"
}

# =============================
# ⚙️ 環境設定
# =============================
setup_environment() {
    log_step "環境設定を構成中..."
    
    # .env ファイルの確認と作成
    if [[ ! -f ".env" ]]; then
        log_warn ".env ファイルが見つかりません。.env.example からコピーします。"
        cp .env.example .env
        log_warn "⚠️  .env ファイルを編集して適切な値を設定してください。"
        
        if [[ "$DEPLOY_MODE" == "production" ]]; then
            log_error "本番環境では .env ファイルの設定が必須です。"
            exit 1
        fi
    fi
    
    # ディレクトリの作成
    local directories=("logs" "data" "uploads" "backups" "monitoring")
    
    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
        log_info "ディレクトリを作成: $dir"
    done
    
    # ログファイルの作成
    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"
    
    log_success "環境設定完了"
}

# =============================
# 🧪 テスト実行
# =============================
run_tests() {
    if [[ "${NO_TESTS:-false}" == "true" ]]; then
        log_warn "テストがスキップされました"
        return 0
    fi
    
    log_step "テストを実行中..."
    
    # 仮想環境の確認とアクティベート
    if [[ -d "venv" ]]; then
        source venv/bin/activate
    elif [[ -d ".venv" ]]; then
        source .venv/bin/activate
    else
        log_warn "仮想環境が見つかりません。グローバル環境でテストを実行します。"
    fi
    
    # 依存関係のインストール確認
    if [[ -f "requirements-test.txt" ]] && command -v pip &> /dev/null; then
        log_info "テスト用依存関係をインストール中..."
        pip install -r requirements-test.txt --quiet
    fi
    
    # テストの実行
    if [[ -f "tests/test_runner.py" ]]; then
        log_info "Stripe機能テストを実行中..."
        python tests/test_runner.py --mode quick --no-coverage
        
        if [[ $? -ne 0 ]]; then
            log_error "テストが失敗しました。デプロイを中止します。"
            exit 1
        fi
    else
        log_warn "テストランナーが見つかりません。基本的なテストをスキップ。"
    fi
    
    log_success "テスト完了"
}

# =============================
# 💾 バックアップ作成
# =============================
create_backup() {
    if [[ "${CREATE_BACKUP:-false}" == "true" ]]; then
        log_step "バックアップを作成中..."
        
        local backup_timestamp=$(date +"%Y%m%d_%H%M%S")
        local backup_path="$BACKUP_DIR/backup_$backup_timestamp"
        
        mkdir -p "$backup_path"
        
        # データベースバックアップ（PostgreSQL）
        if docker-compose ps postgres | grep -q "Up"; then
            log_info "データベースをバックアップ中..."
            docker-compose exec -T postgres pg_dump -U pdf_user pdf_paypal_db > "$backup_path/database_backup.sql"
        fi
        
        # 設定ファイルのバックアップ
        cp .env "$backup_path/.env.backup" 2>/dev/null || log_warn ".env ファイルのバックアップをスキップ"
        
        # アップロードファイルのバックアップ
        if [[ -d "uploads" ]]; then
            tar -czf "$backup_path/uploads_backup.tar.gz" uploads/
        fi
        
        # ログファイルのバックアップ
        if [[ -d "logs" ]]; then
            tar -czf "$backup_path/logs_backup.tar.gz" logs/
        fi
        
        log_success "バックアップ作成完了: $backup_path"
    fi
}

# =============================
# 🏗️ アプリケーションビルド
# =============================
build_application() {
    log_step "アプリケーションをビルド中..."
    
    # 古いイメージの削除
    log_info "古いイメージを削除中..."
    docker-compose down --remove-orphans
    
    # イメージのビルド
    log_info "新しいイメージをビルド中..."
    docker-compose build --no-cache
    
    if [[ $? -ne 0 ]]; then
        log_error "ビルドが失敗しました。"
        exit 1
    fi
    
    log_success "ビルド完了"
}

# =============================
# 🚀 アプリケーションデプロイ
# =============================
deploy_application() {
    log_step "アプリケーションをデプロイ中..."
    
    # 環境固有の設定
    case "$DEPLOY_MODE" in
        "development")
            export FLASK_ENV=development
            export DEBUG=true
            ;;
        "staging")
            export FLASK_ENV=staging
            export DEBUG=false
            ;;
        "production")
            export FLASK_ENV=production
            export DEBUG=false
            ;;
    esac
    
    # サービスの起動
    log_info "サービスを起動中..."
    docker-compose up -d
    
    # ヘルスチェック
    log_info "ヘルスチェックを実行中..."
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -f http://localhost:8080/health &> /dev/null; then
            log_success "アプリケーションが正常に起動しました"
            break
        fi
        
        if [[ $attempt -eq $max_attempts ]]; then
            log_error "ヘルスチェックが失敗しました"
            docker-compose logs app
            exit 1
        fi
        
        log_info "ヘルスチェック試行 $attempt/$max_attempts..."
        sleep 10
        ((attempt++))
    done
    
    log_success "デプロイ完了"
}

# =============================
# 📊 デプロイ後確認
# =============================
post_deploy_checks() {
    log_step "デプロイ後の確認を実行中..."
    
    # サービス状態の確認
    log_info "サービス状態を確認中..."
    docker-compose ps
    
    # ログの確認
    log_info "最新のログを確認中..."
    docker-compose logs --tail=50 app
    
    # エンドポイントの確認
    local endpoints=("/" "/health" "/settings")
    
    for endpoint in "${endpoints[@]}"; do
        local url="http://localhost:8080$endpoint"
        if curl -f "$url" &> /dev/null; then
            log_success "エンドポイント確認: $endpoint ✓"
        else
            log_warn "エンドポイント確認: $endpoint ✗"
        fi
    done
    
    # ディスク使用量の確認
    log_info "ディスク使用量:"
    df -h | grep -E "(Filesystem|/dev/)"
    
    # Docker リソース使用量
    log_info "Docker リソース使用量:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
    
    log_success "デプロイ後確認完了"
}

# =============================
# 🧹 クリーンアップ
# =============================
cleanup() {
    log_step "クリーンアップを実行中..."
    
    # 未使用のDockerイメージを削除
    docker image prune -f
    
    # 古いバックアップの削除（30日以上古い）
    if [[ -d "$BACKUP_DIR" ]]; then
        find "$BACKUP_DIR" -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
    fi
    
    log_success "クリーンアップ完了"
}

# =============================
# 📱 通知送信
# =============================
send_notification() {
    local status="$1"
    local message="$2"
    
    # Slack通知（SLACK_WEBHOOK_URL が設定されている場合）
    if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"[${PROJECT_NAME}] ${DEPLOY_MODE} デプロイ ${status}: ${message}\"}" \
            "$SLACK_WEBHOOK_URL" &> /dev/null || true
    fi
    
    # メール通知（ADMIN_EMAIL が設定されている場合）
    if [[ -n "${ADMIN_EMAIL:-}" ]] && command -v mail &> /dev/null; then
        echo "${message}" | mail -s "[${PROJECT_NAME}] デプロイ ${status}" "$ADMIN_EMAIL" || true
    fi
}

# =============================
# 🚨 エラーハンドリング
# =============================
handle_error() {
    local exit_code=$?
    local line_number=$1
    
    log_error "スクリプトがエラーで終了しました（終了コード: $exit_code, 行: $line_number）"
    
    # ログファイルに詳細を記録
    {
        echo "$(date): デプロイエラー"
        echo "モード: $DEPLOY_MODE"
        echo "終了コード: $exit_code"
        echo "行番号: $line_number"
        echo "---"
    } >> "$LOG_FILE"
    
    # 通知送信
    send_notification "失敗" "エラーで終了（終了コード: $exit_code）"
    
    exit $exit_code
}

# エラートラップの設定
trap 'handle_error $LINENO' ERR

# =============================
# 🎯 メイン実行フロー
# =============================
main() {
    # 引数の解析
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help)
                show_help
                exit 0
                ;;
            --backup)
                CREATE_BACKUP=true
                shift
                ;;
            --no-tests)
                NO_TESTS=true
                shift
                ;;
            --force)
                FORCE=true
                shift
                ;;
            *)
                if [[ "$1" =~ ^(development|staging|production)$ ]]; then
                    DEPLOY_MODE="$1"
                else
                    log_error "不明なオプション: $1"
                    show_help
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # 開始ログ
    echo -e "${PURPLE}"
    echo "=================================="
    echo "PDF-PayPal-Stripe システム デプロイ"
    echo "=================================="
    echo "モード: $DEPLOY_MODE"
    echo "開始時刻: $(date)"
    echo -e "${NC}"
    
    # 確認プロンプト
    if [[ "${FORCE:-false}" != "true" ]]; then
        if [[ "$DEPLOY_MODE" == "production" ]]; then
            log_warn "本番環境にデプロイしようとしています。"
            read -p "続行しますか？ (yes/no): " -r
            if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                log_info "デプロイを中止しました。"
                exit 0
            fi
        fi
    fi
    
    # デプロイフローの実行
    local start_time=$(date +%s)
    
    check_prerequisites
    setup_environment
    run_tests
    create_backup
    build_application
    deploy_application
    post_deploy_checks
    cleanup
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # 成功ログ
    echo -e "${GREEN}"
    echo "=================================="
    echo "デプロイ成功！"
    echo "=================================="
    echo "モード: $DEPLOY_MODE"
    echo "実行時間: ${duration}秒"
    echo "完了時刻: $(date)"
    echo ""
    echo "アクセスURL:"
    echo "  - アプリケーション: http://localhost:8080"
    echo "  - Grafana: http://localhost:3000"
    echo "  - Prometheus: http://localhost:9090"
    echo -e "${NC}"
    
    # 成功通知
    send_notification "成功" "${DEPLOY_MODE}環境に正常にデプロイされました（実行時間: ${duration}秒）"
    
    # ログファイルに記録
    {
        echo "$(date): デプロイ成功"
        echo "モード: $DEPLOY_MODE"
        echo "実行時間: ${duration}秒"
        echo "---"
    } >> "$LOG_FILE"
}

# =============================
# 🏁 スクリプト実行
# =============================
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
