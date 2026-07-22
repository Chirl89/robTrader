import os
import sys
import json
import csv
import subprocess
import atexit
import logging
from flask import Flask, jsonify, request, render_template, send_file

app = Flask(
    __name__, 
    template_folder=os.path.join("web", "templates"), 
    static_folder=os.path.join("web", "static")
)

# Bot process holder
bot_process = None
log_file_handle = None

# Set up paths
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(ROOT_DIR, "data_logs")
def get_account_suffix():
    import hashlib
    import dotenv
    env_path = os.path.join(ROOT_DIR, ".env")
    key = "default"
    if os.path.exists(env_path):
        config = dotenv.dotenv_values(env_path)
        key = config.get("ALPACA_API_KEY_ID", "default") or "default"
    is_sim = (key == "default" or not key.strip())
    prefix = "sim" if is_sim else "alpaca"
    key_clean = "simulator" if is_sim else key.strip()
    h = hashlib.md5(key_clean.encode()).hexdigest()[:8]
    return f"{prefix}_{h}"

def get_file_path(filename_template):
    suffix = get_account_suffix()
    name = filename_template.format(suffix=suffix)
    return os.path.join(LOG_DIR, name)

def get_portfolio_state_file():
    return get_file_path("portfolio_state_{suffix}.json")

def get_trades_file():
    return get_file_path("trades_log_{suffix}.csv")

def get_tax_report_file():
    return get_file_path("spanish_tax_report_{suffix}.csv")

def get_dividends_file():
    return get_file_path("dividends_log_{suffix}.csv")

def get_bot_stdout_file():
    return get_file_path("bot_stdout_{suffix}.log")

def get_portfolio_history_file():
    return get_file_path("portfolio_history_{suffix}.csv")

def get_analysis_file():
    return get_file_path("analysis_state_{suffix}.json")

os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("robTrader.Web")

def get_data_provider():
    import dotenv
    dotenv.load_dotenv(os.path.join(ROOT_DIR, ".env"), override=True)
    use_alpaca = bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_SECRET_KEY"))
    if use_alpaca:
        from data.alpaca_provider import AlpacaProvider
        return AlpacaProvider()
    else:
        from data.yahoo_provider import YahooProvider
        return YahooProvider()

def get_broker():
    import dotenv
    dotenv.load_dotenv(os.path.join(ROOT_DIR, ".env"), override=True)
    use_alpaca = bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_SECRET_KEY"))
    if use_alpaca:
        from broker.alpaca_broker import AlpacaBroker
        return AlpacaBroker()
    else:
        from broker.simulator_broker import SimulatorBroker
        return SimulatorBroker(initial_cash=10000.0)

def get_bot_status():
    global bot_process
    is_running = bot_process is not None and bot_process.poll() is None
    return "running" if is_running else "stopped"

def cleanup_bot_process():
    global bot_process, log_file_handle
    if bot_process is not None and bot_process.poll() is None:
        logger.info("Terminating bot process during web server cleanup...")
        bot_process.terminate()
        try:
            bot_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            bot_process.kill()
        bot_process = None
    if log_file_handle is not None:
        log_file_handle.close()
        log_file_handle = None

atexit.register(cleanup_bot_process)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def api_status():
    status = get_bot_status()
    portfolio = {}
    if os.path.exists(get_portfolio_state_file()):
        try:
            with open(get_portfolio_state_file(), 'r', encoding='utf-8') as f:
                portfolio = json.load(f)
        except Exception as e:
            logger.error(f"Error reading portfolio state: {e}")
            
    # Default fallback
    if not portfolio:
        portfolio = {
            'timestamp': None,
            'status': 'inactive',
            'cash': 0.0,
            'portfolio_value': 0.0,
            'positions': {}
        }
        
    return jsonify({
        'bot_status': status,
        'portfolio': portfolio
    })

@app.route('/api/control', methods=['POST'])
def api_control():
    global bot_process, log_file_handle
    data = request.json or {}
    action = data.get('action')
    
    if action == 'start':
        if get_bot_status() == 'running':
            return jsonify({'status': 'error', 'message': 'Bot is already running.'}), 400
            
        logger.info("Starting bot background process...")
        try:
            python_exec = sys.executable
            # Ensure correct executable (use venv python if available)
            venv_python_win = os.path.join(ROOT_DIR, "venv", "Scripts", "python.exe")
            venv_python_nix = os.path.join(ROOT_DIR, "venv", "bin", "python")
            if os.path.exists(venv_python_win):
                python_exec = venv_python_win
            elif os.path.exists(venv_python_nix):
                python_exec = venv_python_nix
                
            # Create/truncate stdout file
            log_file_handle = open(get_bot_stdout_file(), "w", encoding="utf-8")
            
            # Start loop
            import dotenv
            current_env = os.environ.copy()
            env_path = os.path.join(ROOT_DIR, ".env")
            if os.path.exists(env_path):
                file_env = dotenv.dotenv_values(env_path)
                for k, v in file_env.items():
                    if v is not None:
                        current_env[k] = v
            
            bot_process = subprocess.Popen(
                [python_exec, "-c", "from strategy.scheduler import TradingScheduler; TradingScheduler().start_loop()"],
                stdout=log_file_handle,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=ROOT_DIR,
                env=current_env
            )
            return jsonify({'status': 'success', 'message': 'Bot process started.'})
        except Exception as e:
            logger.error(f"Failed to start bot process: {e}")
            return jsonify({'status': 'error', 'message': f'Failed to start: {e}'}), 500
            
    elif action == 'stop':
        if get_bot_status() == 'stopped':
            return jsonify({'status': 'error', 'message': 'Bot is not running.'}), 400
            
        logger.info("Stopping bot process...")
        cleanup_bot_process()
        return jsonify({'status': 'success', 'message': 'Bot process stopped.'})
        
    return jsonify({'status': 'error', 'message': 'Invalid action.'}), 400

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    env_path = os.path.join(ROOT_DIR, ".env")
    
    if request.method == 'GET':
        config = {}
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            config[k.strip()] = v.strip()
            except Exception as e:
                logger.error(f"Error reading .env: {e}")
                
        # Fill standard fallbacks
        defaults = {
            'ALPACA_API_KEY_ID': '',
            'ALPACA_SECRET_KEY': '',
            'ALPACA_ENV': 'paper',
            'ORDER_TYPE': 'market',
            'DEFAULT_TRADING_SYMBOLS': 'AAPL,MSFT,TSLA,BTCUSD',
            'DYNAMIC_SCAN': 'False',
            'DYNAMIC_SCAN_INDEX': 'SP500',
            'DYNAMIC_STOCK_LIMIT': '15',
            'BUY_THRESHOLD': '0.25',
            'SELL_THRESHOLD': '-0.25',
            'HISTORICAL_DAYS': '120',
            'PORTFOLIO_REFRESH_SECS': '15',
            'REANALYZE_INTERVAL_MINS': '60',
            'MAX_POSITION_SIZE_PCT': '0.10',
            'DAILY_LOSS_LIMIT_PCT': '0.02'
        }
        for k, v in defaults.items():
            if k not in config:
                config[k] = v
                
        return jsonify(config)
        
    elif request.method == 'POST':
        data = request.json or {}
        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write("# Alpaca API Credentials\n")
                f.write(f"ALPACA_API_KEY_ID={data.get('ALPACA_API_KEY_ID', '').strip()}\n")
                f.write(f"ALPACA_SECRET_KEY={data.get('ALPACA_SECRET_KEY', '').strip()}\n")
                f.write(f"ALPACA_ENV={data.get('ALPACA_ENV', 'paper').strip()}\n")
                f.write(f"ORDER_TYPE={data.get('ORDER_TYPE', 'market').strip()}\n\n")
                
                f.write("# Strategy Configuration\n")
                f.write(f"DEFAULT_TRADING_SYMBOLS={data.get('DEFAULT_TRADING_SYMBOLS', '').strip()}\n")
                f.write(f"BUY_THRESHOLD={data.get('BUY_THRESHOLD', '0.25').strip()}\n")
                f.write(f"SELL_THRESHOLD={data.get('SELL_THRESHOLD', '-0.25').strip()}\n")
                f.write(f"HISTORICAL_DAYS={data.get('HISTORICAL_DAYS', '120').strip()}\n\n")
                
                f.write("# Dynamic Scanner Configuration\n")
                f.write(f"DYNAMIC_SCAN={data.get('DYNAMIC_SCAN', 'False').strip()}\n")
                f.write(f"DYNAMIC_SCAN_INDEX={data.get('DYNAMIC_SCAN_INDEX', 'SP500').strip()}\n")
                f.write(f"DYNAMIC_STOCK_LIMIT={data.get('DYNAMIC_STOCK_LIMIT', '15').strip()}\n\n")
                
                f.write("# Refresh intervals\n")
                f.write(f"PORTFOLIO_REFRESH_SECS={data.get('PORTFOLIO_REFRESH_SECS', '15').strip()}\n")
                f.write(f"REANALYZE_INTERVAL_MINS={data.get('REANALYZE_INTERVAL_MINS', '60').strip()}\n\n")
                
                f.write("# Safety limits\n")
                f.write(f"MAX_POSITION_SIZE_PCT={data.get('MAX_POSITION_SIZE_PCT', '0.10').strip()}\n")
                f.write(f"DAILY_LOSS_LIMIT_PCT={data.get('DAILY_LOSS_LIMIT_PCT', '0.02').strip()}\n")
                
            # Reload the new environment keys into Flask process memory
            import dotenv
            dotenv.load_dotenv(env_path, override=True)
            
            return jsonify({'status': 'success', 'message': 'Configuration saved successfully.'})
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return jsonify({'status': 'error', 'message': f'Failed to save config: {e}'}), 500

@app.route('/api/trades', methods=['GET'])
def api_trades():
    trades = []
    if os.path.exists(get_trades_file()):
        try:
            with open(get_trades_file(), 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    trades.append(row)
            
            # Enrich trades with name using cache to prevent slow repeated queries
            data_provider = get_data_provider()
            name_cache = {}
            for row in trades:
                sym = row.get('symbol')
                if sym:
                    if sym not in name_cache:
                        try:
                            fundamentals = data_provider.get_fundamentals(sym)
                            name_cache[sym] = fundamentals.get('name') or sym
                        except Exception:
                            name_cache[sym] = sym
                    row['name'] = name_cache[sym]
        except Exception as e:
            logger.error(f"Error reading trades file: {e}")
    # Return latest trades first
    return jsonify(trades[::-1])

@app.route('/api/tax', methods=['GET'])
def api_tax():
    # Dynamically generate latest tax report
    try:
        from reporting.tax_exporter import TaxExporter
        exporter = TaxExporter()
        report = exporter.generate_tax_report()
        
        # Load trades list from generated report file
        events = []
        if os.path.exists(get_tax_report_file()):
            with open(get_tax_report_file(), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 7:
                        events.append({
                            'symbol': row[0],
                            'buy_date': row[1],
                            'sell_date': row[2],
                            'qty': float(row[3]),
                            'acquisition_val': float(row[4]),
                            'sale_val': float(row[5]),
                            'gain_loss': float(row[6])
                        })
                        
        # Enrich tax events with name using cache
        data_provider = get_data_provider()
        name_cache = {}
        for ev in events:
            sym = ev['symbol']
            if sym not in name_cache:
                try:
                    fundamentals = data_provider.get_fundamentals(sym)
                    name_cache[sym] = fundamentals.get('name') or sym
                except Exception:
                    name_cache[sym] = sym
            ev['name'] = name_cache[sym]
            
        report['events'] = events
        return jsonify(report)
    except Exception as e:
        logger.error(f"Error compiling tax report: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/tax/download', methods=['GET'])
def api_tax_download():
    try:
        from reporting.tax_exporter import TaxExporter
        exporter = TaxExporter()
        exporter.generate_tax_report()
        
        if os.path.exists(get_tax_report_file()):
            return send_file(
                get_tax_report_file(),
                mimetype='text/csv',
                as_attachment=True,
                download_name='spanish_tax_report.csv'
            )
        else:
            return jsonify({'status': 'error', 'message': 'No tax report generated yet.'}), 404
    except Exception as e:
        logger.error(f"Error downloading tax report: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/trades/download', methods=['GET'])
def api_trades_download():
    try:
        if os.path.exists(get_trades_file()):
            return send_file(
                get_trades_file(),
                mimetype='text/csv',
                as_attachment=True,
                download_name='trades_log.csv'
            )
        else:
            return jsonify({'status': 'error', 'message': 'No trades logged yet.'}), 404
    except Exception as e:
        logger.error(f"Error downloading trades log: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/alpaca_orders', methods=['GET'])
def api_alpaca_orders():
    try:
        data_provider = get_data_provider()
        broker = get_broker()
        orders = broker.get_orders()
        
        # Enrich orders with name using cache
        name_cache = {}
        for o in orders:
            sym = o['symbol']
            if sym not in name_cache:
                try:
                    fundamentals = data_provider.get_fundamentals(sym)
                    name_cache[sym] = fundamentals.get('name') or sym
                except Exception:
                    name_cache[sym] = sym
            o['name'] = name_cache[sym]
            
        return jsonify(orders)
    except Exception as e:
        logger.error(f"Error fetching live orders: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/active_orders', methods=['GET'])
def api_active_orders():
    try:
        data_provider = get_data_provider()
        broker = get_broker()
        orders = broker.get_open_orders()
        
        # Enrich orders with name using cache
        name_cache = {}
        for o in orders:
            sym = o['symbol']
            if sym not in name_cache:
                try:
                    fundamentals = data_provider.get_fundamentals(sym)
                    name_cache[sym] = fundamentals.get('name') or sym
                except Exception:
                    name_cache[sym] = sym
            o['name'] = name_cache[sym]
            
        return jsonify(orders)
    except Exception as e:
        logger.error(f"Error fetching active orders: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/analysis', methods=['GET'])
def api_analysis():
    analysis_file = get_analysis_file()
    state = {}
    if os.path.exists(analysis_file):
        try:
            with open(analysis_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except Exception as e:
            logger.error(f"Error reading analysis state: {e}")
            
    if not state:
        state = {
            'timestamp': None,
            'buy_threshold': 0.25,
            'sell_threshold': -0.25,
            'evaluations': {}
        }
    return jsonify(state)

@app.route('/api/portfolio_history', methods=['GET'])
def api_portfolio_history():
    history_file = get_portfolio_history_file()
    points = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if row and len(row) >= 3:
                        points.append({
                            'timestamp': row[0],
                            'portfolio_value': float(row[1]),
                            'cash': float(row[2])
                        })
        except Exception as e:
            logger.error(f"Error reading portfolio history: {e}")
            
    # Read current state to retrieve start_day_portfolio_value
    state_file = get_portfolio_state_file()
    start_val = 100000.0  # default fallback
    current_val = 100000.0
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
                start_val = state_data.get('start_day_portfolio_value', start_val)
                current_val = state_data.get('portfolio_value', current_val)
        except Exception:
            pass
            
    initial_val = points[0]['portfolio_value'] if points else start_val
    
    daily_diff = current_val - start_val
    daily_pct = (daily_diff / start_val * 100.0) if start_val > 0 else 0.0
    
    global_diff = current_val - initial_val
    global_pct = (global_diff / initial_val * 100.0) if initial_val > 0 else 0.0
    
    return jsonify({
        'history': points,
        'daily': {
            'difference': round(daily_diff, 2),
            'percentage': round(daily_pct, 2)
        },
        'global': {
            'difference': round(global_diff, 2),
            'percentage': round(global_pct, 2)
        }
    })

@app.route('/api/logs', methods=['GET'])
def api_logs():
    lines = []
    if os.path.exists(get_bot_stdout_file()):
        try:
            with open(get_bot_stdout_file(), 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            lines = [f"Error reading log file: {e}"]
    else:
        lines = ["Bot is stopped. No execution output log available yet."]
        
    # Return last 100 lines
    return jsonify(lines[-100:])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
