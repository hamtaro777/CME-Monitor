#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TopstepX APIを使用して**全ての**CME先物銘柄を取得するスクリプト（Windows対応版）

改善点:
1. Windows/Linux両対応のパス処理
2. APIレスポンスの詳細なデバッグ情報を表示
3. ページネーション対応（存在する場合）
4. 複数の検索方法を試行
5. より詳細なエラーハンドリング
"""

import requests
import pandas as pd
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()
from pathlib import Path


class TopstepXClient:
    """TopstepX APIクライアント（改良版）"""
    
    def __init__(self, username, api_key, debug=True):
        """
        初期化
        
        Args:
            username (str): TopstepXユーザー名
            api_key (str): TopstepX APIキー
            debug (bool): デバッグモード
        """
        self.username = username
        self.api_key = api_key
        self.base_url = "https://api.topstepx.com/api"
        self.session_token = None
        self.debug = debug
        
    def authenticate(self):
        """
        TopstepX APIに認証してセッショントークンを取得
        
        Returns:
            bool: 認証成功時True、失敗時False
        """
        url = f"{self.base_url}/Auth/loginKey"
        payload = {
            "userName": self.username,
            "apiKey": self.api_key
        }
        
        try:
            print("🔐 TopstepX APIに認証中...")
            response = requests.post(
                url, 
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if self.debug:
                    print(f"\n🔍 認証レスポンス:")
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                
                if data.get('success'):
                    self.session_token = data.get('token')
                    print("✅ 認証成功!")
                    return True
                else:
                    print(f"❌ 認証失敗: {data.get('message', '不明なエラー')}")
                    return False
            else:
                print(f"❌ HTTPエラー: {response.status_code}")
                print(f"レスポンス: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ エラー発生: {e}")
            return False
    
    def get_all_contracts_detailed(self):
        """
        全契約を取得（詳細なデバッグ情報付き）
        
        Returns:
            list: 契約情報のリスト
        """
        if not self.session_token:
            print("❌ 先にauthenticate()を実行してください")
            return None
        
        url = f"{self.base_url}/Contract/search"
        headers = {
            "Authorization": f"Bearer {self.session_token}",
            "Content-Type": "application/json"
        }
        
        # 方法1: 空の検索テキストで全件取得を試みる
        print("\n📊 方法1: 空の検索テキストで全銘柄取得...")
        payload = {
            "searchText": "",
            "live": False
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if self.debug:
                    print(f"\n🔍 APIレスポンスの構造:")
                    print(f"レスポンスキー: {list(data.keys())}")
                    
                    # ページネーション情報をチェック
                    if 'totalCount' in data:
                        print(f"総件数: {data['totalCount']}")
                    if 'pageSize' in data:
                        print(f"ページサイズ: {data['pageSize']}")
                    if 'currentPage' in data:
                        print(f"現在のページ: {data['currentPage']}")
                    if 'totalPages' in data:
                        print(f"総ページ数: {data['totalPages']}")
                
                contracts = data.get('contracts', [])
                print(f"✅ {len(contracts)}件の銘柄を取得しました")
                
                # レスポンスに他のデータがある可能性をチェック
                if self.debug and len(data.keys()) > 1:
                    print(f"\n🔍 追加情報:")
                    for key, value in data.items():
                        if key != 'contracts':
                            print(f"  {key}: {value}")
                
                return contracts
            else:
                print(f"❌ HTTPエラー: {response.status_code}")
                print(f"レスポンス: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ エラー発生: {e}")
            return None
    
    def get_contracts_by_category(self):
        """
        カテゴリ別に銘柄を取得（より多くの銘柄を取得するための代替方法）
        
        Returns:
            dict: カテゴリ別の契約情報
        """
        if not self.session_token:
            print("❌ 先にauthenticate()を実行してください")
            return None
        
        print("\n📊 方法2: カテゴリ別検索で銘柄を取得...")
        
        # 主要なCME先物のプレフィックス（拡張版）
        categories = {
            '株価指数': [
                # Standard E-mini
                'ES', 'NQ', 'YM', 'RTY', 
                # International
                'NKD', 'NIY',  # Nikkei 225
                # Micro E-mini
                'MES', 'MNQ', 'M2K', 'MYM',
                # その他
                'EMD', 'SSG'
            ],
            '通貨': [
                'EC', '6E', '6J', '6B', '6C', '6A', '6S', '6N', '6M',
                'DX', 'E7', 'J7', 'AUD', 'CAD', 'CHF', 'EUR', 'GBP', 'JPY', 'NZD'
            ],
            'エネルギー': [
                'CL', 'NG', 'RB', 'HO', 'BZ', 'QG', 'QM',
                'MCL', 'MGC'  # Micro contracts
            ],
            '貴金属': [
                'GC', 'SI', 'HG', 'PL', 'PA',
                'QO', 'QI', 'MGC', 'SIL'  # Micro & E-micro
            ],
            '農産物': [
                'ZC', 'ZS', 'ZW', 'ZL', 'ZM', 'ZO', 'ZR',
                'CT', 'KC', 'SB', 'CC', 'OJ',
                'DC', 'DY'  # Dairy
            ],
            '畜産': ['LE', 'HE', 'GF', 'DC'],
            '債券': [
                'ZB', 'ZN', 'ZF', 'ZT', 'UB',
                'TWE', 'FV'  # Ultra T-Bond, Five Year
            ],
            '仮想通貨': ['BTC', 'ETH', 'MBT', 'MET'],
            'ボラティリティ': ['VX', 'VXM'],
            'その他': ['BRN', 'LBS']
        }
        
        all_contracts = {}
        
        for category, prefixes in categories.items():
            print(f"\n  {category}カテゴリを検索中...")
            category_contracts = []
            
            for prefix in prefixes:
                contracts = self.search_contracts(search_text=prefix, live=False, silent=True)
                if contracts:
                    # 重複を避けるため、本当にそのプレフィックスで始まるものだけを追加
                    filtered = [c for c in contracts if c.get('name', '').startswith(prefix)]
                    category_contracts.extend(filtered)
            
            # 重複を除去（idで判定）
            unique_contracts = []
            seen_ids = set()
            for contract in category_contracts:
                contract_id = contract.get('id')
                if contract_id and contract_id not in seen_ids:
                    unique_contracts.append(contract)
                    seen_ids.add(contract_id)
            
            all_contracts[category] = unique_contracts
            print(f"    → {len(unique_contracts)}件")
        
        return all_contracts
    
    def search_contracts(self, search_text="", live=False, silent=False):
        """
        契約を検索
        
        Args:
            search_text (str): 検索テキスト
            live (bool): ライブデータかどうか
            silent (bool): ログ出力を抑制
            
        Returns:
            list: 契約情報のリスト
        """
        if not self.session_token:
            return None
        
        url = f"{self.base_url}/Contract/search"
        headers = {
            "Authorization": f"Bearer {self.session_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "searchText": search_text,
            "live": live
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                contracts = data.get('contracts', [])
                
                if not silent:
                    print(f"検索 '{search_text}': {len(contracts)}件")
                
                return contracts
            else:
                if not silent:
                    print(f"❌ 検索エラー: {response.status_code}")
                return None
                
        except Exception as e:
            if not silent:
                print(f"❌ エラー: {e}")
            return None


def merge_contract_lists(list1, list2):
    """
    2つの契約リストをマージ（重複除去）
    
    Args:
        list1 (list): 契約リスト1
        list2 (list): 契約リスト2
        
    Returns:
        list: マージされた契約リスト
    """
    if not list1:
        return list2 or []
    if not list2:
        return list1 or []
    
    merged = list1.copy()
    existing_ids = {c.get('id') for c in list1}
    
    for contract in list2:
        contract_id = contract.get('id')
        if contract_id and contract_id not in existing_ids:
            merged.append(contract)
            existing_ids.add(contract_id)
    
    return merged


def create_output_directory():
    """
    出力ディレクトリを作成（存在しない場合）
    
    Returns:
        Path: 出力ディレクトリのパス
    """
    # カレントディレクトリに output フォルダを作成
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    return output_dir


def main():
    """メイン処理"""
    print("="*100)
    print("🚀 TopstepX 全CME銘柄取得ツール（Windows対応版）")
    print("="*100)
    print()
    
    # 認証情報
    USERNAME = os.getenv("TOPSTEPX_USERNAME")
    API_KEY = os.getenv("TOPSTEPX_API_KEY")

    # 環境変数チェック
    if not USERNAME or not API_KEY:
        print("❌ エラー: 環境変数が設定されていません")
        print("\n.envファイルに以下を設定してください:")
        print("TOPSTEPX_USERNAME=your_username")
        print("TOPSTEPX_API_KEY=your_api_key")
        print("\n詳細はREADME.mdを参照してください。")
        return
    
    # 出力ディレクトリを作成
    output_dir = create_output_directory()
    print(f"📁 出力ディレクトリ: {output_dir.absolute()}\n")
    
    # APIクライアント作成（デバッグモード有効）
    client = TopstepXClient(USERNAME, API_KEY, debug=True)
    
    # 認証
    if not client.authenticate():
        print("\n❌ 認証に失敗しました。プログラムを終了します。")
        return
    
    print("\n" + "="*100)
    
    # 方法1: 標準的な全件取得
    contracts_method1 = client.get_all_contracts_detailed()
    
    # 方法2: カテゴリ別検索
    contracts_by_category = client.get_contracts_by_category()
    
    # NKDを明示的に検索（デバッグ）
    print("\n" + "="*100)
    print("🔍 NKD（日経225）を明示的に検索")
    print("="*100)
    nkd_contracts = client.search_contracts(search_text="NKD", live=False, silent=False)
    if nkd_contracts and len(nkd_contracts) > 0:
        print(f"✅ NKD銘柄が見つかりました: {len(nkd_contracts)}件")
        for contract in nkd_contracts[:3]:
            print(f"   • {contract.get('name')}: {contract.get('description')}")
    else:
        print("⚠️ NKD銘柄が見つかりませんでした")
        print("   TopstepXアカウントで日経225データへのアクセス権があるか確認してください")
    
    # NIY（日経225円建て）も検索
    niy_contracts = client.search_contracts(search_text="NIY", live=False, silent=False)
    if niy_contracts and len(niy_contracts) > 0:
        print(f"✅ NIY銘柄が見つかりました: {len(niy_contracts)}件")
        for contract in niy_contracts[:3]:
            print(f"   • {contract.get('name')}: {contract.get('description')}")
    
    print("="*100)
    
    # カテゴリ別の契約を1つのリストにまとめる
    contracts_method2 = []
    if contracts_by_category:
        for category, contracts in contracts_by_category.items():
            contracts_method2.extend(contracts)
    
    # 両方の結果をマージ
    print("\n" + "="*100)
    print("📊 取得結果のマージ")
    print("="*100)
    
    print(f"\n方法1（空検索）: {len(contracts_method1) if contracts_method1 else 0}件")
    print(f"方法2（カテゴリ別）: {len(contracts_method2)}件")
    
    all_contracts = merge_contract_lists(contracts_method1, contracts_method2)
    print(f"\nマージ後の総件数: {len(all_contracts)}件")
    
    if not all_contracts:
        print("\n❌ 銘柄の取得に失敗しました。")
        return
    
    # 銘柄情報を整理
    print("\n" + "="*100)
    print("📋 取得した銘柄の詳細")
    print("="*100)
    
    # カテゴリ別に分類
    categorized = {}
    for contract in all_contracts:
        name = contract.get('name', '')
        
        # カテゴリ判定
        if name.startswith(('ES', 'NQ', 'YM', 'RTY', 'NKD', 'NIY', 'MES', 'MNQ', 'M2K', 'MYM', 'EMD', 'SSG')):
            category = '株価指数'
        elif name.startswith(('GC', 'SI', 'HG', 'PL', 'PA', 'QO', 'QI', 'MGC', 'SIL')):
            category = '貴金属'
        elif name.startswith(('CL', 'NG', 'RB', 'HO', 'BZ', 'QG', 'QM', 'MCL')):
            category = 'エネルギー'
        elif name.startswith(('ZC', 'ZS', 'ZW', 'ZL', 'ZM', 'ZO', 'ZR', 'CT', 'KC', 'SB', 'CC', 'OJ', 'DC', 'DY')):
            category = '農産物'
        elif name.startswith(('EC', '6E', '6J', '6B', '6C', '6A', '6S', '6N', '6M', 'DX', 'E7', 'J7', 'AUD', 'CAD', 'CHF', 'EUR', 'GBP', 'JPY', 'NZD')):
            category = '通貨'
        elif name.startswith(('ZB', 'ZN', 'ZF', 'ZT', 'UB', 'TWE', 'FV')):
            category = '債券'
        elif name.startswith(('LE', 'HE', 'GF')):
            category = '畜産'
        elif name.startswith(('BTC', 'ETH', 'MBT', 'MET')):
            category = '仮想通貨'
        elif name.startswith(('VX', 'VXM')):
            category = 'ボラティリティ'
        else:
            category = 'その他'
        
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(contract)
    
    # カテゴリ別に表示
    for category, contracts in sorted(categorized.items()):
        print(f"\n【{category}】 {len(contracts)}件")
        for contract in contracts[:5]:  # 各カテゴリの最初の5件を表示
            name = contract.get('name', 'N/A')
            desc = contract.get('description', 'N/A')
            if len(desc) > 50:
                desc = desc[:47] + "..."
            print(f"  • {name:<10s} - {desc}")
        
        if len(contracts) > 5:
            print(f"  ... 他 {len(contracts) - 5}件")
    
    # CSVに保存
    print("\n" + "="*100)
    print("💾 データ保存")
    print("="*100)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 全データをCSVに保存
    csv_filename = output_dir / f"all_cme_contracts_{timestamp}.csv"
    df = pd.DataFrame(all_contracts)
    df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
    print(f"\n✅ 全銘柄データを保存: {csv_filename}")
    print(f"   総件数: {len(all_contracts)}件")
    
    # カテゴリ別にもCSVを保存
    for category, contracts in categorized.items():
        # ファイル名に使えない文字を置換
        safe_category = category.replace('/', '_').replace('\\', '_')
        category_filename = output_dir / f"cme_{safe_category}_{timestamp}.csv"
        df_cat = pd.DataFrame(contracts)
        df_cat.to_csv(category_filename, index=False, encoding='utf-8-sig')
        print(f"   {category}: {len(contracts)}件 → {category_filename.name}")
    
    # JSONでも保存
    json_filename = output_dir / f"all_cme_contracts_{timestamp}.json"
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(all_contracts, f, indent=2, ensure_ascii=False)
    print(f"\n✅ JSON形式でも保存: {json_filename}")
    
    print("\n" + "="*100)
    print("🎉 処理完了!")
    print("="*100)
    print(f"\n取得した銘柄数: {len(all_contracts)}件")
    print(f"保存場所: {output_dir.absolute()}")
    print("\n次のステップ:")
    print("  1. outputフォルダ内のCSVファイルで全銘柄を確認")
    print("  2. 特定の銘柄の履歴データを取得")
    print("  3. リアルタイム監視アプリで監視")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ ユーザーによって中断されました")
    except Exception as e:
        print(f"\n❌ 予期しないエラー: {e}")
        import traceback
        traceback.print_exc()