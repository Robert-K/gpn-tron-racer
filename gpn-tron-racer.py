import socket, os, datetime, random, time, sys, traceback

# Large grids can cause stack overflows, so we increase the recursion limit
sys.setrecursionlimit(3000)

if os.name == 'nt':
    import msvcrt
else:
    print('Warning: Non-Windows OS detected, input will not work as expected :(')

HOST = 'gpn-tron.duckdns.org'
PORT = 4000

USER = os.getenv('GPN_TRON_USER')
PASS = os.getenv('GPN_TRON_PASS')

if not USER or not PASS:
    print('Please set GPN_TRON_USER and GPN_TRON_PASS environment variables')
    exit(1)

print(f'User: {USER}')

current_game = None

input_dir = 'up'

sock = None

wins = 0
losses = 0

won_last_game = False

exit_requested = False

error_text = None

best_score = 0

overlap = False

my_grid = None

last_cmd = None

enemy_near = False

valid_moves = []

best_dir = None

flood_grid = None

# Send chat message
def chat(msg):
    sock.sendall(compose('chat', msg))

player_emojis = [
    { 'head': '🟤', 'body': '🟫' },
    { 'head': '🟣', 'body': '🟪' },
    { 'head': '🔴', 'body': '🟥' },
    { 'head': '🟢', 'body': '🟩' },
    { 'head': '🟠', 'body': '🟧' },
    { 'head': '🟡', 'body': '🟨' },
]

# Initialize a new game
def init_game(width, height, player_id):
    global current_game, player_emojis
    width = int(width)
    height = int(height)
    player_id = int(player_id)
    current_game = { 'width' : width, 'height' : height, 'player_id' : player_id, 'players' : {}, 'grid' : [ ['X'] * height for _ in range(width)], 'tick' : 0, 'alive': True}
    random.shuffle(player_emojis)
    print(f'New game started: {width}x{height} | Player ID: {player_id}')
    chat(f'GLHF! {wins}W {losses}L')

def get_player_emoji(player_id, head=False):
    pair = player_emojis[player_id % len(player_emojis)]
    return pair['head'] if head else pair['body']

# Get player by position, returns None if no player is there
def get_player(x, y):
    x, y = wrap(x, y)
    for player in current_game['players']:
        if current_game['players'][player]['x'] == x and current_game['players'][player]['y'] == y:
            return player
    return None

# Print the current grid with emojis, highlight my player and show its direction, also highlight other player heads
def print_grid():
    os.system('cls' if os.name=='nt' else 'clear')
    for y in range(current_game['height']):
        for x in range(current_game['width']):
            if current_game['grid'][x][y] == current_game['player_id']:
                if current_game['players'][current_game['player_id']]['x'] == x and current_game['players'][current_game['player_id']]['y'] == y:
                    if input_dir == 'up':
                        print('⬆️ ', end='')
                    elif input_dir == 'down':
                        print('⬇️ ', end='')
                    elif input_dir == 'left':
                        print('⬅️ ', end='')
                    elif input_dir == 'right':
                        print('➡️ ', end='')
                else:
                    print('🟦', end='')
            elif current_game['grid'][x][y] in current_game['players']:
                print(get_player_emoji(current_game['grid'][x][y], get_player(x,y) is not None), end='')
            else:
                if my_grid and my_grid[x][y] > 0:
                    print('◾', end='')
                else:
                    print('⬛', end='')
        print()

def print_stats():
    print(f'🕑 Tick {"{:03d}".format(current_game["tick"])} at {datetime.datetime.now().strftime("%H:%M:%S")}')
    print(f'{"⚔️" if overlap else "🛡️"}  {"😱" if enemy_near else "😊"} {"{:.1f}".format(best_score)} {"🎯" if best_dir else "❓"}')
    print(f'{ "⬆️" if "up" in valid_moves else "  "}  {"⬅️" if "left" in valid_moves else "  "}  {"➡️" if "right" in valid_moves else "  "}  {"⬇️" if "down" in valid_moves else "  "}')
    print(f'{"{:03d}".format(wins)} 🏆  {"{:03d}".format(losses)} 💀  {"{:0.2f}".format(wins / (wins + losses)) if wins + losses > 0 else "N/A"} ⚖️   🐍 {len(current_game["players"])}')

def move(dir):
    sock.sendall(compose('move', dir))

# Wrap around the grid
def wrap(x, y):
    if x < 0: x = current_game['width'] - 1
    if x >= current_game['width']: x = 0
    if y < 0: y = current_game['height'] - 1
    if y >= current_game['height']: y = 0
    return x, y

# Return a new 2D grid with 0 for empty spaces and -1 for occupied spaces
def flatten_grid(grid):
    return [[0 if grid[x][y] == 'X' else -1 for y in range(current_game['height'])] for x in range(current_game['width'])]

# Breadth-first search to calculate the area of a player
def bfs(queue, grid):
    while queue:
        x, y = queue.pop(0)
        for (nx, ny), _ in adj(x, y):
            if grid[nx][ny] == 0:
                grid[nx][ny] = grid[x][y] + 1
                queue.append((nx, ny))
    return grid

# Compare two reach grids and return the difference in score
def compare_grids(mine, theirs):
    global overlap
    score = 0
    for x in range(current_game['width']):
        for y in range(current_game['height']):
            if mine[x][y] == -1:
                continue
            if mine[x][y] != 0 and mine[x][y] < theirs[x][y]:
                score += 1
                overlap = True
            elif theirs[x][y] != 0 and mine[x][y] > theirs[x][y]:
                score -= 1 / (len(current_game["players"]) + 1)
                overlap = True
    return score

# Return the adjacent cells of a cell and the direction to get there
def adj(x, y):
    dir_pairs = []
    for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
        nx, ny = wrap(x + dx, y + dy)
        dir_pairs.append(((nx, ny), (dx, dy)))
    return dir_pairs

# Return the valid adjacent cells ('X') of a cell as [(x, y), (dx, dy)]
def valid_adj(x, y):
    return [(pos, dir) for pos, dir in adj(x, y) if current_game['grid'][pos[0]][pos[1]] == 'X']

# Flood fill to measure the area around a point
def flood_fill(x, y):
    global flood_grid
    area = 0
    heads = 0
    x, y = wrap(x, y)
    # Run flood fill in all directions, incrementing area and heads
    if flood_grid[x][y] == 'X':
        flood_grid[x][y] = 'F'
        temp_area, temp_heads = flood_fill(x, y-1)
        area += temp_area
        heads += temp_heads
        temp_area, temp_heads = flood_fill(x, y+1)
        area += temp_area
        heads += temp_heads
        temp_area, temp_heads = flood_fill(x-1, y)
        area += temp_area
        heads += temp_heads
        temp_area, temp_heads = flood_fill(x+1, y)
        area += temp_area
        heads += temp_heads
        area += 1
        return area, heads
    player = get_player(x, y)
    if player and player != current_game['player_id']:
        heads += 1
    return 0, heads

# Count adjacent heads, excluding the player itself
def adjacent_heads(x, y):
    heads = 0
    player = get_player(x, y-1)
    if player and player != current_game['player_id']:
        heads += 1
    player = get_player(x, y+1)
    if player and player != current_game['player_id']:
        heads += 1
    player = get_player(x-1, y)
    if player and player != current_game['player_id']:
        heads += 1
    player = get_player(x+1, y)
    if player and player != current_game['player_id']:
        heads += 1
    return heads

# Evaluate a direction based on available area, prefer areas with less heads
def evaluate_direction(x, y):
    global flood_grid
    flood_grid = [row[:] for row in current_game['grid']]
    x, y = wrap(x, y)
    area, heads = flood_fill(x, y)
    value = area - heads - adjacent_heads(x, y)
    for enemy in current_game['players']:
        if enemy != current_game['player_id']:
            enemy_x = current_game['players'][enemy]['x']
            enemy_y = current_game['players'][enemy]['y']
            flood_grid = [row[:] for row in current_game['grid']]
            flood_grid[x][y] = 'F'
            enemy_area, enemy_heads = flood_fill(enemy_x, enemy_y)
            value -= enemy_area * 0.2
    return value if value > 0 else area - adjacent_heads(x, y)

# Calculate the next move based on available area, prefer areas with less heads
def calculate_move_old():
    global input_dir, flood_grid
    x = current_game['players'][current_game['player_id']]['x']
    y = current_game['players'][current_game['player_id']]['y']
    flood_grid = [row[:] for row in current_game['grid']]
    options = [
        {'dir': 'up', 'value': evaluate_direction(x, y-1)},
        {'dir': 'down', 'value': evaluate_direction(x, y+1)},
        {'dir': 'left', 'value': evaluate_direction(x-1, y)},
        {'dir': 'right', 'value': evaluate_direction(x+1, y)}
    ]
    options.sort(key=lambda x: x['value'], reverse=True)
    input_dir = options[0]['dir']

# Calculate the next move
def calculate_move():
    global input_dir, best_score, overlap, my_grid, enemy_near, valid_moves, best_dir
    x, y = current_game['players'][current_game['player_id']]['x'], current_game['players'][current_game['player_id']]['y']
    best_score = -1000
    best_dir = None
    valid_moves = []
    for (nx, ny), (dx, dy) in valid_adj(x, y):
        valid_moves.append(translate_dir(dx, dy))
        my_grid = flatten_grid(current_game['grid'])
        my_grid[nx][ny] = -1
        my_grid = bfs([(nx, ny)], my_grid)
        overlap = False
        enemy_near = False
        score = 0
        enemy_heads = []
        next_cells = valid_adj(nx, ny)
        for enemy in current_game['players']:
            if enemy != current_game['player_id']:
                enemy_heads.append((current_game['players'][enemy]['x'], current_game['players'][enemy]['y']))
                for (mx, my), _ in adj(current_game['players'][enemy]['x'], current_game['players'][enemy]['y']):
                    if current_game['grid'][mx][my] == current_game['player_id']:
                        enemy_near = True
                        score -= 50
                    for (ex, ey), _ in next_cells:
                        if ex == mx and ey == my:
                            score -= 10
        enemy_grid = flatten_grid(current_game['grid'])
        enemy_grid = bfs(enemy_heads, enemy_grid)
        score += compare_grids(my_grid, enemy_grid)
        if score > best_score:
            best_score = score
            best_dir = (dx, dy)
        my_grid[nx][ny] = 1
    if overlap and best_dir:
        input_dir = translate_dir(*best_dir)
    calculate_move_old()

# Translate a direction to a string
def translate_dir(dx, dy):
    if dx == 0 and dy == 1:
        return 'down'
    if dx == 0 and dy == -1:
        return 'up'
    if dx == 1 and dy == 0:
        return 'right'
    if dx == -1 and dy == 0:
        return 'left'
    return 'down'

# Handle game tick
def handle_tick():
    if not current_game: return
    current_game['tick'] += 1
    if not current_game['alive']: return
    calculate_move()
    move(input_dir)

# Handle player position update
def handle_pos(player_id, x, y):
    player_id = int(player_id)
    x = int(x)
    y = int(y)
    current_game['players'][player_id] = { 'x' : x, 'y' : y }
    current_game['grid'][x][y] = player_id

# Handle my death
def handle_die(*player_ids):
    if not current_game: return
    for player_id in player_ids:
        player_id = int(player_id)
        # print(f'Player {player_id} died!')
        current_game['players'].pop(player_id)
        for x in range(current_game['width']):
            for y in range(current_game['height']):
                if current_game['grid'][x][y] == player_id:
                    current_game['grid'][x][y] = 'X'
        if player_id == current_game['player_id'] and exit_requested:
            exit(0)

# Handle my loss
def handle_loss(wins, losses):
    global won_last_game
    won_last_game = False
    globals()['wins'] = int(wins)
    globals()['losses'] = int(losses)
    handle_die(current_game['player_id'])
    current_game['alive'] = False
    if exit_requested:
        exit(0)
    # print(f'You lost :( Wins: {wins} | Losses: {losses}')

# Handle my win
def handle_win(wins, losses):
    global won_last_game
    won_last_game = True
    globals()['wins'] = int(wins)
    globals()['losses'] = int(losses)
    if exit_requested:
        exit(0)
    # print(f'You won! Wins: {wins} | Losses: {losses}')
    
def handle_error(error):
    global error_text
    print(f'Error: {error}')
    error_text = error

# Compose a command to send to the server
def compose(*args):
    return '|'.join(args).encode('utf-8') + b'\n'

# Parse a command received from the server
def parse(data):
    data = data.decode('utf-8').strip()
    cmd, *args = data.split('|')
    return cmd, args

# Handlers for commands
handlers = {
    'motd': lambda motd: print(f'MOTD: {motd}'),
    'error': handle_error,
    'game': init_game,
    'tick': handle_tick,
    'pos': handle_pos,
    'die': handle_die,
    'message': lambda player_id, message: print(f'Player {player_id} says: {message}'),
    'win': handle_win,
    'lose': handle_loss,
    'player': lambda player_id, name: None
}

# Handle a response
def handle_cmd(response):
    global last_cmd
    cmd, args = parse(response)
    last_cmd = cmd
    if cmd not in handlers:
        print(f'UNKNOWN COMMAND: {cmd}({",".join(args)})')
        return
    handlers[cmd](*args)

# Map keyboard input to directions
input_map = {
    b'w': 'up',
    b'a': 'left',
    b's': 'down',
    b'd': 'right',
    b'K': 'left',
    b'M': 'right',
    b'H': 'up',
    b'P': 'down',
}

def handle_input():
    global input_dir, exit_requested
    if os.name != 'nt': return
    if msvcrt.kbhit():
        key = msvcrt.getch()
        if key in input_map:
            input_dir = input_map[key]
            move(input_dir)
        # Exit on 'q' or 'esc'
        if key == b'q' or key == b'\x1b':
            exit_requested = True
            if not current_game or not current_game['alive']:
                exit(0)

while True:
    try:
        # Connect to the server
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            sock = s
            s.connect((HOST, PORT))
            s.settimeout(1)
            print(f'Connected to {HOST}:{PORT}')
            s.sendall(compose('join', USER, PASS))
            try:
                while 'life is good':
                    line = b''
                    while not line.endswith(b'\n'):
                        try:
                            line += s.recv(1)
                            handle_input()
                        except socket.timeout as e:
                            err = e.args[0]
                            if err == 'timed out':
                                handle_input()
                                continue
                            else:
                                print(e)
                                exit(1)
                    handle_cmd(line)
                    if current_game and last_cmd == 'tick':
                        print_grid()
                        print_stats()
                        if error_text:
                            print(f'🚨 {error_text}')
                        if exit_requested:
                            print('🚪 Exiting after current game...')
            
            except KeyboardInterrupt:
                exit(0)
    except Exception:
        error_text = traceback.format_exc()
        print(error_text)
        time.sleep(1)