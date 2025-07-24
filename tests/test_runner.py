#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stripe機能テストランナー
全自動テストの実行とレポート生成
"""

import pytest
import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path
import subprocess
import argparse

# パスの設定
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class StripeTestRunner:
    """Stripeテストランナークラス"""
    
    def __init__(self, output_dir="test_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def run_all_tests(self, generate_coverage=True, include_slow=False):
        """全テストの実行"""
        print("🚀 Stripe機能包括テスト開始")
        print("=" * 80)
        
        test_results = {}
        overall_start_time = time.time()
        
        # テストスイート定義
        test_suites = [
            {
                'name': 'integration',
                'file': 'test_stripe_integration.py',
                'description': 'Stripe統合テスト',
                'markers': []
            },
            {
                'name': 'performance',
                'file': 'test_performance.py', 
                'description': 'パフォーマンステスト',
                'markers': ['not slow'] if not include_slow else []
            },
            {
                'name': 'security',
                'file': 'test_security.py',
                'description': 'セキュリティテスト',
                'markers': []
            },
            {
                'name': 'integration_full',
                'file': 'test_integration.py',
                'description': '統合テスト',
                'markers': []
            }
        ]
        
        # 各テストスイートを実行
        for suite in test_suites:
            print(f"\n📋 {suite['description']} 実行中...")
            result = self._run_test_suite(suite, generate_coverage)
            test_results[suite['name']] = result
            
            # 実行結果の簡易表示
            if result['success']:
                print(f"✅ {suite['description']}: {result['passed']}/{result['total']} 成功")
            else:
                print(f"❌ {suite['description']}: {result['passed']}/{result['total']} 成功 (失敗あり)")
        
        overall_end_time = time.time()
        overall_duration = overall_end_time - overall_start_time
        
        # 総合レポート生成
        report_data = {
            'timestamp': self.timestamp,
            'overall_duration': overall_duration,
            'test_results': test_results,
            'summary': self._generate_summary(test_results)
        }
        
        self._generate_html_report(report_data)
        self._generate_json_report(report_data)
        
        print(f"\n🏁 全テスト完了 (実行時間: {overall_duration:.2f}秒)")
        print(f"📊 レポート: {self.output_dir}/test_report_{self.timestamp}.html")
        
        return report_data
    
    def _run_test_suite(self, suite, generate_coverage):
        """個別テストスイートの実行"""
        test_file = os.path.join(os.path.dirname(__file__), suite['file'])
        
        if not os.path.exists(test_file):
            return {
                'success': False,
                'error': f"テストファイルが見つかりません: {test_file}",
                'passed': 0,
                'total': 0,
                'duration': 0
            }
        
        # pytest実行コマンド構築
        cmd = [
            sys.executable, '-m', 'pytest',
            test_file,
            '-v',
            '--tb=short',
            '--json-report',
            f'--json-report-file={self.output_dir}/pytest_{suite["name"]}_{self.timestamp}.json'
        ]
        
        # マーカー追加
        for marker in suite['markers']:
            cmd.extend(['-m', marker])
        
        # カバレッジ追加
        if generate_coverage:
            cmd.extend([
                '--cov=.',
                '--cov-report=html:' + str(self.output_dir / f'coverage_{suite["name"]}_{self.timestamp}'),
                '--cov-report=json:' + str(self.output_dir / f'coverage_{suite["name"]}_{self.timestamp}.json')
            ])
        
        try:
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            end_time = time.time()
            
            duration = end_time - start_time
            
            # pytest JSONレポートの解析
            json_report_file = self.output_dir / f'pytest_{suite["name"]}_{self.timestamp}.json'
            
            if json_report_file.exists():
                with open(json_report_file, 'r') as f:
                    pytest_data = json.load(f)
                
                summary = pytest_data.get('summary', {})
                
                return {
                    'success': result.returncode == 0,
                    'passed': summary.get('passed', 0),
                    'failed': summary.get('failed', 0),
                    'skipped': summary.get('skipped', 0),
                    'total': summary.get('total', 0),
                    'duration': duration,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'detailed_results': pytest_data
                }
            else:
                return {
                    'success': result.returncode == 0,
                    'passed': 0,
                    'failed': 0,
                    'skipped': 0,
                    'total': 0,
                    'duration': duration,
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'error': 'JSONレポートが生成されませんでした'
                }
                
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'テスト実行がタイムアウトしました',
                'passed': 0,
                'total': 0,
                'duration': 300
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'テスト実行エラー: {str(e)}',
                'passed': 0,
                'total': 0,
                'duration': 0
            }
    
    def _generate_summary(self, test_results):
        """テスト結果サマリー生成"""
        total_passed = sum(result.get('passed', 0) for result in test_results.values())
        total_failed = sum(result.get('failed', 0) for result in test_results.values())
        total_skipped = sum(result.get('skipped', 0) for result in test_results.values())
        total_tests = sum(result.get('total', 0) for result in test_results.values())
        total_duration = sum(result.get('duration', 0) for result in test_results.values())
        
        success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        return {
            'total_tests': total_tests,
            'total_passed': total_passed,
            'total_failed': total_failed,
            'total_skipped': total_skipped,
            'success_rate': success_rate,
            'total_duration': total_duration,
            'overall_success': total_failed == 0
        }
    
    def _generate_html_report(self, report_data):
        """HTMLレポート生成"""
        html_content = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stripe機能テストレポート - {report_data['timestamp']}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.3/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .test-success {{ background-color: #d1fae5; border-color: #10b981; }}
        .test-failed {{ background-color: #fee2e2; border-color: #ef4444; }}
        .test-skipped {{ background-color: #fef3c7; border-color: #f59e0b; }}
        .metric-card {{ transition: transform 0.2s; }}
        .metric-card:hover {{ transform: translateY(-2px); }}
    </style>
</head>
<body>
    <div class="container py-5">
        <div class="row">
            <div class="col-12">
                <h1 class="mb-4">
                    <i class="bi bi-graph-up"></i> Stripe機能テストレポート
                </h1>
                <p class="text-muted">実行日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}</p>
            </div>
        </div>
        
        <!-- サマリーセクション -->
        <div class="row mb-5">
            <div class="col-12">
                <h2 class="mb-3">📊 テスト結果サマリー</h2>
            </div>
            <div class="col-md-3">
                <div class="card metric-card h-100 border-success">
                    <div class="card-body text-center">
                        <i class="bi bi-check-circle-fill text-success fs-1"></i>
                        <h3 class="mt-2">{report_data['summary']['total_passed']}</h3>
                        <p class="text-muted mb-0">成功</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card metric-card h-100 border-danger">
                    <div class="card-body text-center">
                        <i class="bi bi-x-circle-fill text-danger fs-1"></i>
                        <h3 class="mt-2">{report_data['summary']['total_failed']}</h3>
                        <p class="text-muted mb-0">失敗</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card metric-card h-100 border-warning">
                    <div class="card-body text-center">
                        <i class="bi bi-dash-circle-fill text-warning fs-1"></i>
                        <h3 class="mt-2">{report_data['summary']['total_skipped']}</h3>
                        <p class="text-muted mb-0">スキップ</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card metric-card h-100 border-info">
                    <div class="card-body text-center">
                        <i class="bi bi-clock-fill text-info fs-1"></i>
                        <h3 class="mt-2">{report_data['summary']['total_duration']:.1f}s</h3>
                        <p class="text-muted mb-0">実行時間</p>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 成功率 -->
        <div class="row mb-5">
            <div class="col-12">
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">
                            <i class="bi bi-percent"></i> 成功率
                        </h5>
                        <div class="progress" style="height: 30px;">
                            <div class="progress-bar bg-{'success' if report_data['summary']['success_rate'] >= 95 else 'warning' if report_data['summary']['success_rate'] >= 80 else 'danger'}" 
                                 role="progressbar" 
                                 style="width: {report_data['summary']['success_rate']:.1f}%">
                                {report_data['summary']['success_rate']:.1f}%
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- テストスイート詳細 -->
        <div class="row">
            <div class="col-12">
                <h2 class="mb-3">🧪 テストスイート詳細</h2>
            </div>
        """
        
        # 各テストスイートの詳細
        for suite_name, result in report_data['test_results'].items():
            status_class = 'test-success' if result.get('success', False) else 'test-failed'
            status_icon = 'bi-check-circle-fill text-success' if result.get('success', False) else 'bi-x-circle-fill text-danger'
            
            html_content += f"""
            <div class="col-md-6 mb-4">
                <div class="card {status_class}">
                    <div class="card-header">
                        <h5 class="mb-0">
                            <i class="bi {status_icon}"></i> {suite_name.replace('_', ' ').title()}
                        </h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-6">
                                <p class="mb-1"><strong>成功:</strong> {result.get('passed', 0)}</p>
                                <p class="mb-1"><strong>失敗:</strong> {result.get('failed', 0)}</p>
                            </div>
                            <div class="col-6">
                                <p class="mb-1"><strong>スキップ:</strong> {result.get('skipped', 0)}</p>
                                <p class="mb-1"><strong>実行時間:</strong> {result.get('duration', 0):.2f}s</p>
                            </div>
                        </div>
                        {f'<div class="alert alert-danger mt-2"><small>{result.get("error", "")}</small></div>' if result.get('error') else ''}
                    </div>
                </div>
            </div>
            """
        
        html_content += """
        </div>
        
        <!-- 推奨アクション -->
        <div class="row mt-5">
            <div class="col-12">
                <h2 class="mb-3">💡 推奨アクション</h2>
                <div class="card">
                    <div class="card-body">
        """
        
        if report_data['summary']['overall_success']:
            html_content += """
                        <div class="alert alert-success">
                            <h5><i class="bi bi-check-circle-fill"></i> 全テスト成功</h5>
                            <p class="mb-0">Stripe機能は正常に動作しています。本番環境へのデプロイが可能です。</p>
                        </div>
            """
        else:
            html_content += f"""
                        <div class="alert alert-warning">
                            <h5><i class="bi bi-exclamation-triangle-fill"></i> テスト失敗あり</h5>
                            <p>以下の確認を推奨します：</p>
                            <ul>
                                <li>失敗したテストの詳細確認</li>
                                <li>Stripe API設定の再確認</li>
                                <li>ネットワーク接続の確認</li>
                                <li>必要に応じてコードの修正</li>
                            </ul>
                        </div>
            """
        
        html_content += """
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
        """
        
        # HTMLファイル保存
        html_file = self.output_dir / f'test_report_{self.timestamp}.html'
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def _generate_json_report(self, report_data):
        """JSONレポート生成"""
        json_file = self.output_dir / f'test_report_{self.timestamp}.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    def run_quick_smoke_test(self):
        """クイックスモークテスト"""
        print("🚀 Stripe機能スモークテスト開始")
        print("=" * 50)
        
        # 基本的な機能テストのみ実行
        cmd = [
            sys.executable, '-m', 'pytest',
            os.path.join(os.path.dirname(__file__), 'test_stripe_integration.py::TestStripeAPIConnection::test_stripe_configuration_validation'),
            '-v',
            '--tb=short'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print("✅ スモークテスト成功")
                print("基本機能は正常に動作しています")
            else:
                print("❌ スモークテスト失敗")
                print("詳細な調査が必要です")
                print(result.stderr)
                
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print("❌ スモークテストタイムアウト")
            return False
        except Exception as e:
            print(f"❌ スモークテスト実行エラー: {str(e)}")
            return False


def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description='Stripe機能テストランナー')
    parser.add_argument('--mode', choices=['full', 'quick', 'smoke'], default='full',
                       help='テスト実行モード')
    parser.add_argument('--no-coverage', action='store_true',
                       help='カバレッジレポートをスキップ')
    parser.add_argument('--include-slow', action='store_true',
                       help='時間のかかるテストも実行')
    parser.add_argument('--output-dir', default='test_reports',
                       help='レポート出力ディレクトリ')
    
    args = parser.parse_args()
    
    runner = StripeTestRunner(output_dir=args.output_dir)
    
    if args.mode == 'smoke':
        success = runner.run_quick_smoke_test()
        sys.exit(0 if success else 1)
    elif args.mode == 'quick':
        # クイックテスト（セキュリティテストのみスキップ）
        report = runner.run_all_tests(
            generate_coverage=not args.no_coverage,
            include_slow=False
        )
    else:
        # フルテスト
        report = runner.run_all_tests(
            generate_coverage=not args.no_coverage,
            include_slow=args.include_slow
        )
    
    # 終了コード設定
    success = report['summary']['overall_success']
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()