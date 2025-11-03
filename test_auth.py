# test_topstep_direct.py
import requests
import json

def test_topstep_direct():
    """TopstepX REST API直接接続テスト"""
    try:
        print("TopstepX API接続テスト開始...\n")
        
        # TopstepXの認証エンドポイント
        api_url = "https://api.topstepx.com/api/Auth/loginKey"
        
        payload = {
            "userName": "hiroki777",
            "apiKey": "LGtep8r6Jykj1bTs3f4x1lQ4E/C74b8lWYYmcryblPU="
        }
        
        print(f"接続先: {api_url}")
        print("認証中...\n")
        
        response = requests.post(
            api_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            timeout=30
        )
        
        print(f"ステータスコード: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 認証成功！\n")
            
            # レスポンスの構造を確認
            print("レスポンス内容:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # セッショントークンを取得
            session_token = data.get('sessionToken') or data.get('token') or data.get('data', {}).get('sessionToken')
            
            if session_token:
                print(f"\n✅ セッショントークン取得成功")
                print(f"トークン（最初の20文字）: {session_token[:20]}...")
                
                # トークンをファイルに保存
                with open('session_token.txt', 'w') as f:
                    f.write(session_token)
                print("トークンを session_token.txt に保存しました")
                
                # アカウント情報を取得してみる
                print("\nアカウント情報取得中...")
                accounts_url = "https://api.topstepx.com/api/Account/getAccounts"
                accounts_response = requests.get(
                    accounts_url,
                    headers={
                        "Authorization": f"Bearer {session_token}",
                        "Accept": "application/json"
                    }
                )
                
                print(f"アカウント取得ステータス: {accounts_response.status_code}")
                
                if accounts_response.status_code == 200:
                    accounts = accounts_response.json()
                    print(f"\n✅ アカウント情報取得成功")
                    print(json.dumps(accounts, indent=2, ensure_ascii=False))
                else:
                    print(f"アカウント取得レスポンス: {accounts_response.text}")
            else:
                print("\n⚠️ セッショントークンが見つかりません")
                print("レスポンス全体を確認してください")
            
            return True
        else:
            print(f"❌ 認証失敗")
            print(f"レスポンス: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ タイムアウト: APIサーバーへの接続がタイムアウトしました")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 接続エラー: インターネット接続を確認してください")
        return False
    except Exception as e:
        print(f"❌ エラー発生: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = test_topstep_direct()
    if result:
        print("\n🎉 TopstepX REST API接続テスト成功！次のステップに進めます")
    else:
        print("\n⚠️ 接続テストに失敗しました")