# test_market_data_working.py
import requests
import json
import pandas as pd
from datetime import datetime, timedelta, timezone

class TopstepXAPI:
    def __init__(self, username, api_key):
        self.username = username
        self.api_key = api_key
        self.base_url = "https://api.topstepx.com/api"
        self.session_token = None
    
    def authenticate(self):
        """認証してセッショントークンを取得"""
        url = f"{self.base_url}/Auth/loginKey"
        payload = {
            "userName": self.username,
            "apiKey": self.api_key
        }
        
        response = requests.post(url, json=payload)
        data = response.json()
        
        if data.get('success'):
            self.session_token = data.get('token')
            print("✅ 認証成功")
            return True
        else:
            print(f"❌ 認証失敗: {data}")
            return False
    
    def search_contracts(self, search_text="", live=False):
        """契約を検索"""
        if not self.session_token:
            print("❌ 先に authenticate() を実行してください")
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
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('contracts', [])
        else:
            print(f"❌ 契約検索エラー: {response.status_code}")
            print(f"レスポンス: {response.text}")
            return None
    
    def get_historical_data(self, contract_id, days=30, limit=5000):
        """履歴データを取得"""
        if not self.session_token:
            print("❌ 先に authenticate() を実行してください")
            return None
        
        url = f"{self.base_url}/History/retrieveBars"
        headers = {
            "Authorization": f"Bearer {self.session_token}",
            "Content-Type": "application/json"
        }
        
        # timezone-awareなdatetimeを使用
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        
        payload = {
            "contractId": contract_id,
            "live": False,
            "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "unit": 3,  # Daily bars
            "unitNumber": 1,
            "limit": limit,  # 必須パラメータ
            "includePartialBar": False
        }
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # dataキーまたはbarsキーをチェック
            return data.get('data', data.get('bars', data))
        else:
            print(f"❌ データ取得エラー: {response.status_code}")
            print(f"レスポンス: {response.text}")
            return None


def test_market_data():
    """市場データ取得テスト（完全版）"""
    print("=== TopstepX CME先物データ取得テスト ===\n")
    
    # APIクライアント作成
    api = TopstepXAPI(
        username="hiroki777",
        api_key="LGtep8r6Jykj1bTs3f4x1lQ4E/C74b8lWYYmcryblPU="
    )
    
    # 認証
    if not api.authenticate():
        return
    
    print("\n--- 利用可能なCME先物銘柄 ---\n")
    
    # 全契約を取得
    contracts = api.search_contracts(search_text="", live=False)
    
    if not contracts:
        print("❌ 契約が見つかりませんでした")
        return
    
    print(f"✅ {len(contracts)} 件の契約が見つかりました\n")
    
    # 主要な銘柄を表示
    print("主要銘柄:")
    for contract in contracts:
        name = contract.get('name', 'N/A')
        description = contract.get('description', 'N/A')
        contract_id = contract.get('id', 'N/A')
        print(f"  {name:10s} - {description}")
    
    # ES (E-mini S&P 500) を探す
    print("\n--- E-mini S&P 500 (ES) のデータ取得 ---")
    
    es_contract = None
    for contract in contracts:
        if contract.get('name', '').startswith('ES'):
            es_contract = contract
            break
    
    if not es_contract:
        print("❌ ES契約が見つかりませんでした")
        return
    
    contract_id = es_contract.get('id')
    name = es_contract.get('name')
    description = es_contract.get('description')
    
    print(f"✅ 契約を発見: {name} - {description}")
    print(f"   Contract ID: {contract_id}\n")
    
    # 履歴データを取得
    print("過去60日分の日足データを取得中...")
    bars = api.get_historical_data(contract_id, days=60, limit=100)
    
    if not bars or len(bars) == 0:
        print("❌ データが取得できませんでした")
        return
    
    print(f"✅ {len(bars)} 本のバーを取得\n")
    
    # DataFrameに変換
    df = pd.DataFrame(bars)
    
    print("--- データサンプル（最新5件）---")
    print(df.tail())
    
    print("\n--- 統計情報 ---")
    if 'close' in df.columns:
        print(f"終値平均: ${df['close'].mean():.2f}")
        print(f"最高値: ${df['high'].max():.2f}" if 'high' in df.columns else "")
        print(f"最安値: ${df['low'].min():.2f}" if 'low' in df.columns else "")
        
        # 簡易的なチャイキンボラティリティ計算
        if 'high' in df.columns and 'low' in df.columns:
            df['hl_range'] = df['high'] - df['low']
            ema_hl = df['hl_range'].ewm(span=10).mean()
            chaikin_vol = ((ema_hl - ema_hl.shift(10)) / ema_hl.shift(10)) * 100
            
            print(f"\nチャイキンボラティリティ（最新値）: {chaikin_vol.iloc[-1]:.2f}%")
        
        # ROC計算
        if len(df) > 10:
            roc = ((df['close'].iloc[-1] - df['close'].iloc[-11]) / df['close'].iloc[-11]) * 100
            print(f"ROC (10日): {roc:.2f}%")
    
    # CSVに保存
    filename = f'{name}_data.csv'
    df.to_csv(filename, index=False)
    print(f"\n✅ データを {filename} に保存しました")
    
    # 他の銘柄もテスト
    print("\n--- 他の主要銘柄 ---")
    symbols_to_test = ['NQ', 'GC', 'CL']  # Nasdaq, Gold, Crude Oil
    
    for symbol_prefix in symbols_to_test:
        for contract in contracts:
            if contract.get('name', '').startswith(symbol_prefix):
                name = contract.get('name')
                description = contract.get('description')
                print(f"  {name:10s} - {description}")
                break
    
    print("\n🎉 データ取得テスト完了！")
    print("次のステップ：デスクトップアプリの開発に進めます")
    
    return True


if __name__ == "__main__":
    try:
        test_market_data()
    except Exception as e:
        print(f"\n❌ エラー発生: {e}")
        import traceback
        traceback.print_exc()