# 個別の履歴ファイルの支払いステータスを更新するAPIエンドポイント
@app.route('/api/update_history_payment_statuses/<filename>', methods=['GET'])
@admin_required
def update_history_payment_statuses_api(filename):
    # 特定の履歴ファイルに含まれる未完了の支払いステータスをすべて更新するAPIエンドポイント(管理者専用)
    try:
        # ファイル名のバリデーション
        if not re.match(r'^[\w\-\.]+\.json$', filename):
            logger.warning(f"不正なファイル名形式: {filename}")
            return jsonify({
                'success': False,
                'message': '不正なファイル名形式です'
            }), 400
            
        # 履歴ファイルのパスを取得
        history_file_path = os.path.join(app.config['RESULTS_FOLDER'], filename)
        
        # ファイルが存在するか確認
        if not os.path.exists(history_file_path):
            logger.warning(f"履歴ファイルが見つかりません: {history_file_path}")
            return jsonify({
                'success': False,
                'message': '履歴ファイルが見つかりません'
            }), 404
            
        # 履歴ファイルを読み込む
        try:
            with open(history_file_path, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
        except Exception as e:
            logger.error(f"履歴ファイル読み込みエラー: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'履歴ファイルの読み込みに失敗しました: {str(e)}'
            }), 500
            
        # 更新対象のPayPal注文IDを収集
        order_ids = []
        for item in history_data.get('items', []):
            if item.get('paypal_order_id') and item.get('payment_status') not in ['COMPLETED', 'REFUNDED', 'CANCELLED']:
                order_ids.append(item.get('paypal_order_id'))
        
        if not order_ids:
            logger.info(f"更新対象の注文IDがありません: {filename}")
            return jsonify({
                'success': True,
                'updated_count': 0,
                'message': '更新対象の注文IDがありません'
            })
        
        # 各注文IDの支払いステータスを更新
        updated_count = 0
        error_count = 0
        
        for order_id in order_ids:
            try:
                success, new_status, message = update_payment_status_by_order_id(order_id)
                if success:
                    updated_count += 1
                else:
                    error_count += 1
                    logger.warning(f"注文ID {order_id} の更新に失敗: {message}")
            except Exception as e:
                error_count += 1
                logger.error(f"注文ID {order_id} の更新中に例外発生: {str(e)}")
        
        logger.info(f"履歴ファイル {filename} の支払いステータス更新完了: 更新={updated_count}件, エラー={error_count}件")
        return jsonify({
            'success': True,
            'updated_count': updated_count,
            'error_count': error_count,
            'message': f'{updated_count}件の支払いステータスを更新しました。エラー: {error_count}件'
        })
    
    except Exception as e:
        logger.error(f"履歴ファイル支払いステータス更新API例外: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        }), 500
