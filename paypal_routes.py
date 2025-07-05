#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PayPal支払い処理用のルート定義
支払い完了とキャンセル処理のエンドポイントを提供
"""

import os
import json
import logging
from datetime import datetime
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, session, flash
from payment_status_checker import check_payment_status
from payment_status_updater import update_payment_status_by_order_id
from database import update_payment_status

# ロガーの設定
logger = logging.getLogger(__name__)

# Blueprintの作成
paypal_bp = Blueprint('paypal', __name__, url_prefix='/paypal')

@paypal_bp.route('/success', methods=['GET'])
def payment_success():
    """
    PayPal支払い完了後のリダイレクト先
    支払いが実際に完了したことを確認してから完了ページを表示
    """
    try:
        # PayPalからのクエリパラメータを取得
        token = request.args.get('token')
        order_id = request.args.get('token')  # PayPalはtokenパラメータにorder_idを含める
        
        if not order_id:
            # URLからorder_idを抽出する別の方法を試みる
            payer_id = request.args.get('PayerID')
            if payer_id:
                # 処理履歴からorder_idを検索
                history = get_processing_history_by_order_id(token)
                if history:
                    order_id = history.get('order_id')
        
        if not order_id:
            logger.error("支払い完了ページ: order_idが見つかりません")
            return render_template('payment_error.html', 
                                  error_message="注文IDが見つかりませんでした。管理者にお問い合わせください。",
                                  query_params=dict(request.args))
        
        # 支払いステータスを確認
        logger.info(f"支払いステータスを確認します: order_id={order_id}")
        payment_status = check_payment_status(order_id)
        
        if payment_status == "COMPLETED":
            # 支払いが完了している場合、データベースを更新
            success, new_status, message = update_payment_status_by_order_id(order_id)
            
            if success:
                # 顧客情報は後で実装
                customer_name = '顧客'
                amount = '不明'
                
                return render_template('payment_success.html', 
                                      order_id=order_id,
                                      customer_name=customer_name,
                                      amount=amount,
                                      payment_status=payment_status)
            else:
                logger.error(f"支払いステータス更新失敗: {message}")
                return render_template('payment_error.html', 
                                      error_message=f"支払いは完了しましたが、システムの更新に失敗しました: {message}",
                                      payment_status=payment_status,
                                      order_id=order_id)
        
        elif payment_status == "PENDING":
            # 支払い処理中の場合
            return render_template('payment_pending.html', 
                                  order_id=order_id,
                                  message="支払い処理中です。しばらくお待ちください。")
        
        else:
            # 支払いが失敗または不明な場合
            logger.error(f"支払い失敗または不明なステータス: {payment_status}, order_id={order_id}")
            return render_template('payment_error.html', 
                                  error_message=f"支払い処理に問題が発生しました。ステータス: {payment_status}",
                                  payment_status=payment_status,
                                  order_id=order_id)
    
    except Exception as e:
        logger.error(f"支払い完了ページ処理中のエラー: {str(e)}", exc_info=True)
        return render_template('payment_error.html', 
                              error_message=f"エラーが発生しました: {str(e)}",
                              query_params=dict(request.args))

@paypal_bp.route('/cancel', methods=['GET'])
def payment_cancel():
    """
    PayPal支払いキャンセル後のリダイレクト先
    """
    try:
        # PayPalからのクエリパラメータを取得
        token = request.args.get('token')
        
        logger.info(f"支払いがキャンセルされました: token={token}")
        
        # 顧客情報は後で実装
        customer_name = '顧客'
        
        return render_template('payment_cancel.html', 
                              token=token,
                              customer_name=customer_name)
    
    except Exception as e:
        logger.error(f"支払いキャンセルページ処理中のエラー: {str(e)}", exc_info=True)
        return render_template('payment_error.html', 
                              error_message=f"エラーが発生しました: {str(e)}",
                              query_params=dict(request.args))

@paypal_bp.route('/check_status/<order_id>', methods=['GET'])
def check_payment_status_api(order_id):
    """
    支払いステータスを確認するAPI
    フロントエンドからAjaxで呼び出して支払い状態を確認するために使用
    """
    try:
        if not order_id:
            return jsonify({
                'success': False,
                'message': '注文IDが指定されていません'
            }), 400
        
        # 支払いステータスを確認
        payment_status = check_payment_status(order_id)
        
        # データベースを更新
        if payment_status != "UNKNOWN":
            update_payment_status(order_id, payment_status)
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'status': payment_status,
            'timestamp': str(datetime.now())
        })
    
    except Exception as e:
        logger.error(f"支払いステータス確認API処理中のエラー: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        }), 500
