# cme_monitor_app.py - 環境変数対応版
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import threading
import time
import json
import os
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

class TopstepXAPI:
    def __init__(self, username, api_key):
        self.username = username
        self.api_key = api_key
        self.base_url = "https://api.topstepx.com/api"
        self.session_token = None
    
    def authenticate(self):
        """認証"""
        url = f"{self.base_url}/Auth/loginKey"
        payload = {"userName": self.username, "apiKey": self.api_key}
        response = requests.post(url, json=payload)
        data = response.json()
        
        if data.get('success'):
            self.session_token = data.get('token')
            return True
        return False
    
    def search_contracts(self, search_text="", live=False):
        """契約を検索"""
        if not self.session_token:
            return None
        
        url = f"{self.base_url}/Contract/search"
        headers = {"Authorization": f"Bearer {self.session_token}", "Content-Type": "application/json"}
        payload = {"searchText": search_text, "live": live}
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json().get('contracts', [])
        return None
    
    def get_historical_data(self, contract_id, timeframe="1D", limit=500):
        """履歴データを取得"""
        if not self.session_token:
            return None
        
        url = f"{self.base_url}/History/retrieveBars"
        headers = {"Authorization": f"Bearer {self.session_token}", "Content-Type": "application/json"}
        
        # 時間足に応じたunitとunitNumberの設定
        timeframe_map = {
            "3m": {"unit": 2, "unitNumber": 3, "days": 7},
            "15m": {"unit": 2, "unitNumber": 15, "days": 14},
            "1H": {"unit": 3, "unitNumber": 1, "days": 30},
            "4H": {"unit": 3, "unitNumber": 4, "days": 60},
            "1D": {"unit": 4, "unitNumber": 1, "days": 90}
        }
        
        tf_config = timeframe_map.get(timeframe, timeframe_map["1D"])
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=tf_config["days"])
        
        payload = {
            "contractId": contract_id,
            "live": False,
            "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "unit": tf_config["unit"],
            "unitNumber": tf_config["unitNumber"],
            "limit": limit,
            "includePartialBar": False
        }
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json().get('data', response.json().get('bars', response.json()))
        return None


class MarketAnalyzer:
    """市場分析クラス"""
    
    @staticmethod
    def calculate_indicators(df, debug=False):
        """指標を計算"""
        df = df.copy()
        
        # カラム名の標準化
        rename_map = {
            't': 'time', 'timestamp': 'time', 'datetime': 'time', 'date': 'time',
            'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'
        }
        
        actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
        df = df.rename(columns=actual_rename)
        
        # 時刻カラムを探す
        time_col = None
        for col in ['time', 't', 'timestamp', 'datetime', 'date']:
            if col in df.columns:
                time_col = col
                break
        
        if time_col is None:
            raise ValueError(f"時刻カラムが見つかりません。カラム: {df.columns.tolist()}")
        
        if time_col != 'time':
            df = df.rename(columns={time_col: 'time'})
        
        # 並べ替え
        df = df.sort_values('time').reset_index(drop=True)
        
        # 必須カラムの存在確認
        required_cols = ['high', 'low', 'close']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"必須カラムが不足: {missing_cols}")
        
        # チャイキンボラティリティ(Length=10, ROCLength=12)
        df['hl_range'] = df['high'] - df['low']
        ema_hl = df['hl_range'].ewm(span=10, adjust=False, min_periods=10).mean()
        df['chaikin_vol'] = ((ema_hl - ema_hl.shift(12)) / ema_hl.shift(12)) * 100
        
        # ROC (Rate of Change)
        df['roc'] = ((df['close'] - df['close'].shift(10)) / df['close'].shift(10)) * 100
        
        return df
    
    @staticmethod
    def determine_market_state(chaikin_vol, roc):
        """市場状態を判定"""
        if pd.isna(chaikin_vol) or pd.isna(roc):
            return "データ不足", "⚪"
        
        # スクイーズ
        if chaikin_vol < -10 and abs(roc) < 2:
            return "スクイーズ(エネルギー蓄積)", "🟡"
        
        # トレンド開始
        elif chaikin_vol > 10 and abs(roc) > 3:
            direction = "上昇" if roc > 0 else "下降"
            return f"トレンド開始({direction})", "🔴"
        
        # レンジ
        else:
            return "レンジ", "🟢"


class ConfigManager:
    """設定管理クラス"""
    
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.default_config = {
            "watched_symbols": ['ES', 'NQ', 'GC', 'CL'],
            "timeframe": "1D",
            "auto_update_interval": 60,
            "debug_mode": False,
            "squeeze_threshold": -10,
            "trend_threshold": 10,
            "roc_squeeze_threshold": 2,
            "roc_trend_threshold": 3
        }
    
    def load_config(self):
        """設定を読み込み"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception as e:
                print(f"設定読み込みエラー: {e}")
                return self.default_config
        return self.default_config
    
    def save_config(self, config):
        """設定を保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"設定保存エラー: {e}")
            return False


class SymbolManagerDialog:
    """銘柄管理ダイアログ"""
    
    def __init__(self, parent, all_contracts, watched_symbols, callback):
        self.parent = parent
        self.all_contracts = all_contracts
        self.watched_symbols = watched_symbols.copy()
        self.callback = callback
        
        # ダイアログウィンドウを作成
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("📊 銘柄管理")
        self.dialog.geometry("700x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.setup_ui()
    
    def setup_ui(self):
        """UIセットアップ"""
        # タイトルフレーム
        title_frame = tk.Frame(self.dialog, bg="#2c3e50")
        title_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(
            title_frame,
            text="📊 監視銘柄の管理",
            font=("Arial", 14, "bold"),
            bg="#2c3e50",
            fg="white"
        ).pack(pady=10)
        
        # メインフレーム(2カラム)
        main_frame = tk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 左側:利用可能な銘柄
        left_frame = tk.LabelFrame(main_frame, text="利用可能な銘柄", font=("Arial", 10, "bold"))
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # 銘柄数表示
        self.available_count_label = tk.Label(left_frame, text="", font=("Arial", 9), fg="gray")
        self.available_count_label.pack(anchor=tk.W, padx=10, pady=2)
        
        # 検索フィールド
        search_frame = tk.Frame(left_frame)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(search_frame, text="🔍 検索:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_contracts)
        tk.Entry(search_frame, textvariable=self.search_var, width=20).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # クリアボタン
        tk.Button(
            search_frame,
            text="✕",
            command=lambda: self.search_var.set(""),
            bg="#e74c3c",
            fg="white",
            font=("Arial", 9, "bold"),
            width=3
        ).pack(side=tk.LEFT, padx=2)
        
        # 利用可能な銘柄リスト
        list_frame = tk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.available_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Courier", 10))
        self.available_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.available_listbox.yview)
        
        # リストボックスをダブルクリックで追加
        self.available_listbox.bind('<Double-Button-1>', lambda e: self.add_symbol())
        
        # 契約情報を格納
        self.contract_map = {}
        self.populate_available_contracts()
        
        # 中央:ボタン
        button_frame = tk.Frame(main_frame, width=80)
        button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=50)
        
        tk.Button(
            button_frame,
            text="➡️\n追加",
            command=self.add_symbol,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            width=8,
            height=3
        ).pack(pady=10)
        
        tk.Button(
            button_frame,
            text="⬅️\n削除",
            command=self.remove_symbol,
            bg="#e74c3c",
            fg="white",
            font=("Arial", 10, "bold"),
            width=8,
            height=3
        ).pack(pady=10)
        
        # 右側:監視中の銘柄
        right_frame = tk.LabelFrame(main_frame, text="監視中の銘柄", font=("Arial", 10, "bold"))
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # 銘柄数表示
        self.watched_count_label = tk.Label(right_frame, text="", font=("Arial", 9), fg="gray")
        self.watched_count_label.pack(anchor=tk.W, padx=10, pady=2)
        
        list_frame2 = tk.Frame(right_frame)
        list_frame2.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar2 = tk.Scrollbar(list_frame2)
        scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.watched_listbox = tk.Listbox(list_frame2, yscrollcommand=scrollbar2.set, font=("Courier", 10))
        self.watched_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar2.config(command=self.watched_listbox.yview)
        
        # リストボックスをダブルクリックで削除
        self.watched_listbox.bind('<Double-Button-1>', lambda e: self.remove_symbol())
        
        self.populate_watched_symbols()
        
        # 下部:ボタン
        bottom_frame = tk.Frame(self.dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(
            bottom_frame,
            text="✅ 保存して閉じる",
            command=self.save_and_close,
            bg="#3498db",
            fg="white",
            font=("Arial", 11, "bold"),
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            bottom_frame,
            text="🔍 全銘柄確認",
            command=self.show_all_contracts_debug,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 11, "bold"),
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            bottom_frame,
            text="❌ キャンセル",
            command=self.dialog.destroy,
            bg="#95a5a6",
            fg="white",
            font=("Arial", 11, "bold"),
            width=15
        ).pack(side=tk.RIGHT, padx=5)
    
    def populate_available_contracts(self):
        """利用可能な契約をリストに表示"""
        self.available_listbox.delete(0, tk.END)
        self.contract_map.clear()
        
        if not self.all_contracts:
            self.available_count_label.config(text="銘柄データなし")
            return
        
        # 主要な銘柄を優先表示(E-mini、金属、エネルギー、農産物、通貨など)
        priority_prefixes = [
            # 株価指数
            'ES', 'NQ', 'YM', 'RTY',
            # 貴金属
            'GC', 'SI', 'HG', 'PL',
            # エネルギー
            'CL', 'NG', 'RB', 'HO',
            # 農産物
            'ZC', 'ZS', 'ZW', 'ZL', 'ZM',
            # 通貨
            '6E', '6J', '6B', '6C', '6A', '6S',
            # 債券
            'ZN', 'ZB', 'ZF', 'ZT',
            # その他
            'BTC', 'ETH', 'LE', 'HE', 'GF'
        ]
        
        # 既に表示した銘柄を追跡
        displayed_names = set()
        
        # 優先銘柄を先に表示
        for prefix in priority_prefixes:
            for contract in self.all_contracts:
                name = contract.get('name', '')
                # 監視中でない、かつまだ表示していない銘柄のみ
                if name.startswith(prefix) and name not in self.watched_symbols and name not in displayed_names:
                    description = contract.get('description', 'N/A')
                    display_text = f"{name:10s} - {description}"
                    self.available_listbox.insert(tk.END, display_text)
                    self.contract_map[display_text] = contract
                    displayed_names.add(name)
        
        # その他の銘柄を表示
        for contract in self.all_contracts:
            name = contract.get('name', '')
            # 監視中でない、かつまだ表示していない銘柄のみ
            if name not in self.watched_symbols and name not in displayed_names:
                description = contract.get('description', 'N/A')
                display_text = f"{name:10s} - {description}"
                self.available_listbox.insert(tk.END, display_text)
                self.contract_map[display_text] = contract
                displayed_names.add(name)
        
        # 銘柄数を表示
        total_available = len(self.contract_map)
        total_all = len(self.all_contracts)
        self.available_count_label.config(text=f"利用可能: {total_available}銘柄 (全{total_all}銘柄中)")
    
    def filter_contracts(self, *args):
        """検索フィルタを適用"""
        search_text = self.search_var.get().upper()
        self.available_listbox.delete(0, tk.END)
        
        for display_text, contract in self.contract_map.items():
            if search_text in display_text.upper():
                self.available_listbox.insert(tk.END, display_text)
    
    def populate_watched_symbols(self):
        """監視中の銘柄をリストに表示"""
        self.watched_listbox.delete(0, tk.END)
        
        for symbol in self.watched_symbols:
            # 説明を追加
            description = "N/A"
            for contract in self.all_contracts:
                if contract.get('name', '') == symbol:
                    description = contract.get('description', 'N/A')
                    break
            
            display_text = f"{symbol:10s} - {description}"
            self.watched_listbox.insert(tk.END, display_text)
        
        # 銘柄数を表示
        self.watched_count_label.config(text=f"監視中: {len(self.watched_symbols)}銘柄")
    
    def add_symbol(self):
        """銘柄を追加"""
        selection = self.available_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "追加する銘柄を選択してください")
            return
        
        selected_text = self.available_listbox.get(selection[0])
        contract = self.contract_map.get(selected_text)
        
        if contract:
            symbol = contract.get('name', '')
            if symbol and symbol not in self.watched_symbols:
                self.watched_symbols.append(symbol)
                self.populate_available_contracts()
                self.populate_watched_symbols()
    
    def remove_symbol(self):
        """銘柄を削除"""
        selection = self.watched_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "削除する銘柄を選択してください")
            return
        
        selected_text = self.watched_listbox.get(selection[0])
        symbol = selected_text.split()[0]  # 最初のワード(銘柄コード)を取得
        
        if symbol in self.watched_symbols:
            if len(self.watched_symbols) <= 1:
                messagebox.showwarning("警告", "最低1つの銘柄を監視する必要があります")
                return
            
            self.watched_symbols.remove(symbol)
            self.populate_available_contracts()
            self.populate_watched_symbols()
    
    def show_all_contracts_debug(self):
        """全銘柄をデバッグ用ウィンドウに表示"""
        debug_window = tk.Toplevel(self.dialog)
        debug_window.title("🔍 全銘柄一覧")
        debug_window.geometry("800x600")
        
        # テキストエリア
        text_frame = tk.Frame(debug_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(text_frame, yscrollcommand=scrollbar.set, font=("Courier", 10), wrap=tk.NONE)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # 横スクロールバー
        h_scrollbar = tk.Scrollbar(debug_window, orient=tk.HORIZONTAL)
        h_scrollbar.pack(fill=tk.X, padx=10)
        text_widget.config(xscrollcommand=h_scrollbar.set)
        h_scrollbar.config(command=text_widget.xview)
        
        # 全銘柄情報を表示
        text_widget.insert(tk.END, f"=== 全銘柄一覧 ===\n")
        text_widget.insert(tk.END, f"全契約数: {len(self.all_contracts)}\n")
        text_widget.insert(tk.END, f"監視中: {len(self.watched_symbols)}銘柄\n")
        text_widget.insert(tk.END, f"利用可能: {len(self.all_contracts) - len(self.watched_symbols)}銘柄\n\n")
        
        text_widget.insert(tk.END, f"{'銘柄コード':<15} {'説明':<60} {'状態'}\n")
        text_widget.insert(tk.END, "=" * 100 + "\n")
        
        # 銘柄をソートして表示
        sorted_contracts = sorted(self.all_contracts, key=lambda x: x.get('name', ''))
        
        for contract in sorted_contracts:
            name = contract.get('name', 'N/A')
            description = contract.get('description', 'N/A')
            status = "🟢 監視中" if name in self.watched_symbols else "⚪ 利用可能"
            
            text_widget.insert(tk.END, f"{name:<15} {description:<60} {status}\n")
        
        text_widget.config(state=tk.DISABLED)
        
        # 閉じるボタン
        tk.Button(
            debug_window,
            text="閉じる",
            command=debug_window.destroy,
            bg="#3498db",
            fg="white",
            font=("Arial", 11, "bold")
        ).pack(pady=10)
    
    def save_and_close(self):
        """保存して閉じる"""
        if len(self.watched_symbols) == 0:
            messagebox.showwarning("警告", "最低1つの銘柄を選択してください")
            return
        
        self.callback(self.watched_symbols)
        self.dialog.destroy()


class CMEMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CME先物監視アプリ v5.0 - 環境変数対応版")
        self.root.geometry("1100x750")
        
        # 設定管理
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        
        # 環境変数からAPI認証情報を取得
        self.username = os.getenv('TOPSTEPX_USERNAME')
        self.api_key = os.getenv('TOPSTEPX_API_KEY')
        
        # 認証情報の確認
        if not self.username or not self.api_key:
            messagebox.showerror(
                "環境変数エラー",
                "TopstepX APIの認証情報が設定されていません。\n\n"
                ".envファイルに以下を設定してください:\n"
                "TOPSTEPX_USERNAME=your_username\n"
                "TOPSTEPX_API_KEY=your_api_key\n\n"
                "詳細はREADME.mdを参照してください。"
            )
            self.root.quit()
            return
        
        self.api = None
        
        # 監視銘柄
        self.watched_symbols = self.config.get('watched_symbols', ['ES', 'NQ', 'GC', 'CL'])
        self.timeframe = self.config.get('timeframe', '1D')
        self.debug_mode = self.config.get('debug_mode', False)
        self.contracts = {}
        self.all_contracts = []
        
        # 自動更新スレッド
        self.auto_update_running = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """UI構築"""
        # トップフレーム:ステータス
        top_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_label = tk.Label(
            top_frame, 
            text="🔴 未接続", 
            font=("Arial", 14, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        self.status_label.pack(pady=15)
        
        # 時間足選択フレーム
        timeframe_frame = tk.Frame(self.root, bg="#34495e")
        timeframe_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            timeframe_frame,
            text="⏱️ 時間足:",
            font=("Arial", 11, "bold"),
            bg="#34495e",
            fg="white"
        ).pack(side=tk.LEFT, padx=10)
        
        # 時間足選択ラジオボタン
        self.timeframe_var = tk.StringVar(value=self.timeframe)
        timeframe_options = [
            ("3分足", "3m"),
            ("15分足", "15m"),
            ("1時間足", "1H"),
            ("4時間足", "4H"),
            ("日足", "1D")
        ]
        
        for label, value in timeframe_options:
            tk.Radiobutton(
                timeframe_frame,
                text=label,
                variable=self.timeframe_var,
                value=value,
                font=("Arial", 10),
                bg="#34495e",
                fg="white",
                selectcolor="#2c3e50",
                command=self.on_timeframe_change
            ).pack(side=tk.LEFT, padx=5)
        
        # デバッグモード切り替え
        self.debug_var = tk.BooleanVar(value=self.debug_mode)
        tk.Checkbutton(
            timeframe_frame,
            text="🛠 デバッグモード",
            variable=self.debug_var,
            font=("Arial", 10),
            bg="#34495e",
            fg="white",
            selectcolor="#2c3e50",
            command=self.toggle_debug_mode
        ).pack(side=tk.RIGHT, padx=10)
        
        # ボタンフレーム
        button_frame = tk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Button(
            button_frame,
            text="🔌 接続",
            command=self.connect,
            bg="#27ae60",
            fg="white",
            font=("Arial", 11, "bold"),
            width=10
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            button_frame,
            text="📊 銘柄管理",
            command=self.open_symbol_manager,
            bg="#9b59b6",
            fg="white",
            font=("Arial", 11, "bold"),
            width=12
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            button_frame,
            text="🔄 更新",
            command=self.update_data,
            bg="#3498db",
            fg="white",
            font=("Arial", 11, "bold"),
            width=10
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            button_frame,
            text="⏰ 自動更新開始",
            command=self.start_auto_update,
            bg="#f39c12",
            fg="white",
            font=("Arial", 11, "bold"),
            width=13
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            button_frame,
            text="⏸️ 自動更新停止",
            command=self.stop_auto_update,
            bg="#e67e22",
            fg="white",
            font=("Arial", 11, "bold"),
            width=13
        ).pack(side=tk.LEFT, padx=3)
        
        # 結果表示用テーブル
        table_frame = tk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Treeview(テーブル)
        columns = ("銘柄", "時間足", "状態", "終値", "チャイキンVol", "ROC", "データ時刻", "更新時刻")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)
        
        for col in columns:
            self.tree.heading(col, text=col)
            if col == "銘柄":
                self.tree.column(col, width=100, anchor=tk.CENTER)
            elif col == "時間足":
                self.tree.column(col, width=80, anchor=tk.CENTER)
            elif col in ["データ時刻", "更新時刻"]:
                self.tree.column(col, width=140, anchor=tk.CENTER)
            else:
                self.tree.column(col, width=130, anchor=tk.CENTER)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # ログ表示
        log_frame = tk.LabelFrame(self.root, text="📋 ログ", font=("Arial", 10, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=("Courier", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 初期ログ
        self.log(f"監視銘柄: {', '.join(self.watched_symbols)}")
        self.log(f"時間足: {self.get_timeframe_label(self.timeframe)}")
        self.log(f"デバッグモード: {'ON' if self.debug_mode else 'OFF'}")
        self.log("「接続」ボタンをクリックしてAPIに接続してください")
        
    def get_timeframe_label(self, tf):
        """時間足コードからラベルに変換"""
        tf_map = {
            "3m": "3分足",
            "15m": "15分足",
            "1H": "1時間足",
            "4H": "4時間足",
            "1D": "日足"
        }
        return tf_map.get(tf, tf)
    
    def toggle_debug_mode(self):
        """デバッグモード切り替え"""
        self.debug_mode = self.debug_var.get()
        self.config['debug_mode'] = self.debug_mode
        self.config_manager.save_config(self.config)
        self.log(f"🛠 デバッグモード: {'ON' if self.debug_mode else 'OFF'}")
    
    def on_timeframe_change(self):
        """時間足変更時の処理"""
        self.timeframe = self.timeframe_var.get()
        self.log(f"⏱️ 時間足を変更: {self.get_timeframe_label(self.timeframe)}")
        
        # 設定を保存
        self.config['timeframe'] = self.timeframe
        self.config_manager.save_config(self.config)
        
        # データを更新
        if self.api and self.contracts:
            self.update_data()
    
    def open_symbol_manager(self):
        """銘柄管理ダイアログを開く"""
        if not self.api or not self.all_contracts:
            messagebox.showwarning("警告", "先にAPIに接続してください")
            return
        
        SymbolManagerDialog(self.root, self.all_contracts, self.watched_symbols, self.on_symbols_updated)
    
    def on_symbols_updated(self, new_symbols):
        """銘柄が更新された時の処理"""
        self.watched_symbols = new_symbols
        self.config['watched_symbols'] = self.watched_symbols
        self.config_manager.save_config(self.config)
        
        self.log(f"✅ 監視銘柄を更新: {', '.join(self.watched_symbols)}")
        
        # 契約情報を更新
        self.contracts.clear()
        for symbol_prefix in self.watched_symbols:
            for contract in self.all_contracts:
                if contract.get('name', '') == symbol_prefix:
                    self.contracts[symbol_prefix] = contract
                    break
        
        # データを更新
        self.update_data()
    
    def log(self, message):
        """ログ出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def connect(self):
        """API接続"""
        self.log("TopstepX APIに接続中...")
        self.status_label.config(text="🟡 接続中...")
        
        def connect_thread():
            self.api = TopstepXAPI(self.username, self.api_key)
            
            if self.api.authenticate():
                self.log("✅ 認証成功")
                self.status_label.config(text="🟢 接続済み")
                
                # 全契約情報を取得
                self.all_contracts = self.api.search_contracts()
                if self.all_contracts:
                    self.log(f"✅ {len(self.all_contracts)}件の契約情報を取得")
                    
                    # 監視銘柄の契約を取得
                    for symbol_prefix in self.watched_symbols:
                        for contract in self.all_contracts:
                            if contract.get('name', '') == symbol_prefix:
                                self.contracts[symbol_prefix] = contract
                                self.log(f"✅ {symbol_prefix}: {contract.get('description')}")
                                break
                    
                    self.log(f"監視銘柄数: {len(self.contracts)}")
                else:
                    self.log("❌ 契約情報の取得に失敗")
            else:
                self.log("❌ 認証失敗")
                self.status_label.config(text="🔴 接続失敗")
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def update_data(self):
        """データ更新"""
        if not self.api or not self.contracts:
            self.log("⚠️ 先に接続してください")
            return
        
        self.log(f"データ更新中... ({self.get_timeframe_label(self.timeframe)})")
        
        def update_thread():
            # テーブルをクリア
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            for symbol, contract in self.contracts.items():
                contract_id = contract.get('id')
                name = contract.get('name')
                
                self.log(f"📊 {name} のデータ取得中... ({self.get_timeframe_label(self.timeframe)})")
                
                # データ取得(選択された時間足)
                bars = self.api.get_historical_data(contract_id, timeframe=self.timeframe, limit=500)
                
                if not bars or len(bars) == 0:
                    self.log(f"❌ {name}: データ取得失敗")
                    continue
                
                # DataFrameに変換
                df = pd.DataFrame(bars)
                df = MarketAnalyzer.calculate_indicators(df, debug=self.debug_mode)
                
                # 最新データ
                latest = df.iloc[-1]
                chaikin_vol = latest.get('chaikin_vol', 0)
                roc = latest.get('roc', 0)
                close = latest.get('close', 0)
                data_time = latest.get('time', 'N/A')
                
                # 市場状態判定
                state, emoji = MarketAnalyzer.determine_market_state(chaikin_vol, roc)
                
                # データ時刻をフォーマット
                try:
                    from datetime import datetime as dt
                    data_time_str = dt.fromisoformat(data_time.replace('Z', '+00:00')).strftime("%m/%d %H:%M")
                except:
                    data_time_str = str(data_time)[:16] if len(str(data_time)) > 16 else str(data_time)
                
                # テーブルに追加
                self.tree.insert("", tk.END, values=(
                    f"{emoji} {name}",
                    self.get_timeframe_label(self.timeframe),
                    state,
                    f"${close:.2f}",
                    f"{chaikin_vol:.2f}%" if not pd.isna(chaikin_vol) else "N/A",
                    f"{roc:.2f}%" if not pd.isna(roc) else "N/A",
                    data_time_str,
                    datetime.now().strftime("%H:%M:%S")
                ))
                
                self.log(f"✅ {name}: {state} (CV: {chaikin_vol:.2f}%)")
            
            self.log("🎉 更新完了")
        
        threading.Thread(target=update_thread, daemon=True).start()
    
    def start_auto_update(self):
        """自動更新開始"""
        if self.auto_update_running:
            self.log("⚠️ 自動更新は既に実行中です")
            return
        
        self.auto_update_running = True
        interval = self.config.get('auto_update_interval', 60)
        self.log(f"⏰ 自動更新を開始({interval}秒ごと)")
        
        def auto_update_loop():
            while self.auto_update_running:
                self.update_data()
                time.sleep(interval)
        
        threading.Thread(target=auto_update_loop, daemon=True).start()
    
    def stop_auto_update(self):
        """自動更新停止"""
        if not self.auto_update_running:
            self.log("⚠️ 自動更新は実行されていません")
            return
        
        self.auto_update_running = False
        self.log("⏸️ 自動更新を停止しました")


if __name__ == "__main__":
    root = tk.Tk()
    app = CMEMonitorApp(root)
    root.mainloop()