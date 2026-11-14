"""
Neon Runner — Kivy edition.
Запуск на ПК:      python main.py
Сборка APK:        buildozer -v android debug
"""
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.core.audio import SoundLoader
import json, os, math, random

# ============================================================
# SAVE
# ============================================================
_save_path = None

def get_save_path():
    global _save_path
    if _save_path:
        return _save_path
    try:
        app = App.get_running_app()
        if app:
            _save_path = os.path.join(app.user_data_dir, 'save.json')
            return _save_path
    except Exception:
        pass
    _save_path = os.path.join(os.path.expanduser('~'), '.neon_runner.json')
    return _save_path


def default_save():
    return {
        'coins': 50, 'best': 0, 'best_score': 0, 'runs': 0,
        'up': {'jump': 0, 'double': 0, 'magnet': 0,
               'shield': 0, 'coin': 0, 'revive': 0}
    }


def load_save():
    d = default_save()
    try:
        p = get_save_path()
        if os.path.exists(p):
            with open(p, 'r') as f:
                data = json.load(f)
            d.update({k: v for k, v in data.items() if k != 'up'})
            d['up'].update(data.get('up', {}))
    except Exception:
        pass
    return d


def persist_save(s):
    try:
        with open(get_save_path(), 'w') as f:
            json.dump(s, f)
    except Exception:
        pass


# ============================================================
# UPGRADES
# ============================================================
UPGRADES = [
    {'id': 'jump', 'name': 'Сила прыжка', 'max': 5,
     'costs': [60, 150, 340, 750, 1600],
     'desc': lambda l: 'Базовый прыжок' if l == 0 else f'Высота +{l*7}%'},
    {'id': 'double', 'name': 'Двойной прыжок', 'max': 1,
     'costs': [600],
     'desc': lambda l: 'Прыжок в воздухе' if l == 0 else 'Двойной прыжок доступен'},
    {'id': 'magnet', 'name': 'Магнит', 'max': 5,
     'costs': [100, 220, 450, 900, 1800],
     'desc': lambda l: 'Притягивает монеты' if l == 0 else f'Радиус +{l*8}%'},
    {'id': 'shield', 'name': 'Щит', 'max': 3,
     'costs': [250, 650, 1500],
     'desc': lambda l: 'Поглощает удар' if l == 0 else f'Щитов: {l}'},
    {'id': 'coin', 'name': 'Множитель монет', 'max': 5,
     'costs': [130, 300, 700, 1500, 3200],
     'desc': lambda l: 'Больше монет' if l == 0 else f'+{l*25}% монет'},
    {'id': 'revive', 'name': 'Возрождение', 'max': 1,
     'costs': [1500],
     'desc': lambda l: 'Второй шанс после смерти' if l == 0 else 'Возрождение доступно'},
]

C = {
    'cyan':   (0.22, 0.95, 1.00, 1),
    'pink':   (1.00, 0.24, 0.65, 1),
    'gold':   (1.00, 0.85, 0.24, 1),
    'purple': (0.63, 0.42, 1.00, 1),
    'green':  (0.36, 1.00, 0.62, 1),
}


def clamp(v, a, b):
    return max(a, min(b, v))


# ============================================================
# GAME
# ============================================================
class GameWidget(Widget):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.save = load_save()
        self.sounds = self._load_sounds()
        self.state = 'menu'
        self._init_state()
        self._build_ui()
        self.ground_y = self.height * 0.80
        self.init_run()
        Clock.schedule_interval(self.update, 1/60)
        Window.bind(size=self._on_resize)

    def _load_sounds(self):
        sounds = {}
        try:
            for n in ('jump', 'coin', 'hit', 'buy', 'revive'):
                path = os.path.join('sounds', n + '.wav')
                if os.path.exists(path):
                    s = SoundLoader.load(path)
                    if s:
                        sounds[n] = s
        except Exception:
            pass
        return sounds

    def _play(self, n):
        s = self.sounds.get(n)
        if s:
            try:
                s.play()
            except Exception:
                pass

    # ---------- STATE ----------
    def _init_state(self):
        self.t = 0
        self.bg_time = 0
        self.dist = 0
        self.coins = 0
        self.speed = 0
        self.base_speed = 0
        self.difficulty = 0
        self.obstacles = []
        self.coin_list = []
        self.particles = []
        self.spawn_timer = 0
        self.shake = 0
        self.flash = 0
        self.invuln = 0
        self.revive_used = False
        self.last_beam = False
        self.player = None
        self.gravity = 0
        self.jump_power = 0
        self.touch_start_y = 0
        self.touch_moved = False

    def init_run(self):
        ph = clamp(self.height * 0.085, 34, 76)
        pw = ph * 0.72
        self.stand_h, self.stand_w = ph, pw
        self.slide_h = ph * 0.50
        self.slide_w = pw * 1.55

        self.gravity = self.height * 5.2
        jump_mult = 1 + self.save['up']['jump'] * 0.07
        self.jump_power = math.sqrt(2 * self.gravity * ph * 2.8 * jump_mult)

        self.base_speed = max(220, min(self.width * 0.85, self.height * 0.62))
        self.speed = self.base_speed

        self.obstacles, self.coin_list, self.particles = [], [], []
        self.dist = self.coins = 0
        self.difficulty = 0
        self.spawn_timer = 1.15
        self.shake = self.flash = self.invuln = 0
        self.revive_used = False
        self.last_beam = False
        self.t = 0
        self.ground_y = self.height * 0.80

        self.player = {
            'x': self.width * 0.20, 'y': self.ground_y - ph,
            'w': pw, 'h': ph, 'vy': 0,
            'on_ground': True, 'jumps': 0,
            'sliding': False, 'slide_timer': 0,
            'shield': self.save['up']['shield'],
        }

    def _on_resize(self, *a):
        self.ground_y = self.height * 0.80
        if hasattr(self, '_stars'):
            del self._stars
        if self.player:
            p = self.player
            if p['on_ground'] or p['y'] + p['h'] > self.ground_y:
                p['y'] = self.ground_y - p['h']

    # ---------- UI ----------
    def _mk_btn(self, text, cb, color=None, size_hint=(None, None), size=(220, 52)):
        bg = color or C['cyan']
        b = Button(text=text, size_hint=size_hint, size=size,
                   background_normal='', background_color=bg,
                   color=(0.02, 0.07, 0.10, 1), font_size=16, bold=True)
        b.bind(on_release=lambda *_: cb())
        return b

    def _build_ui(self):
        self.ui_root = FloatLayout()
        self.add_widget(self.ui_root)
        self.menu_ui = self._build_menu()
        self.shop_ui = self._build_shop()
        self.dead_ui = self._build_dead()
        self.hud = self._build_hud()
        for w in (self.menu_ui, self.shop_ui, self.dead_ui, self.hud):
            self.ui_root.add_widget(w)
        self._update_ui_visibility()

    def _build_menu(self):
        box = BoxLayout(orientation='vertical', size_hint=(0.85, 0.75),
                        pos_hint={'center_x': 0.5, 'center_y': 0.5}, spacing=12)
        t = Label(text='NEON\nRUNNER', font_size=46, bold=True, color=C['cyan'],
                  halign='center', size_hint=(1, 0.32))
        t.bind(size=t.setter('text_size'))
        box.add_widget(t)
        self.menu_stats = Label(text='', font_size=14, color=C['gold'],
                                 halign='center', size_hint=(1, 0.14))
        self.menu_stats.bind(size=self.menu_stats.setter('text_size'))
        box.add_widget(self.menu_stats)
        box.add_widget(self._mk_btn('▶  ИГРАТЬ', self.start_game,
                                     size_hint=(1, None), size=(0, 54)))
        box.add_widget(self._mk_btn('🛠  УЛУЧШЕНИЯ', self.show_shop,
                                     color=C['pink'],
                                     size_hint=(1, None), size=(0, 54)))
        h = Label(text='Тап / Пробел — прыжок\nСвайп вниз / ↓ — подкат',
                  font_size=12, color=(1, 1, 1, 0.55), halign='center',
                  size_hint=(1, 0.12))
        h.bind(size=h.setter('text_size'))
        box.add_widget(h)
        self._refresh_menu_stats()
        return box

    def _build_shop(self):
        box = BoxLayout(orientation='vertical', size_hint=(0.95, 0.92),
                        pos_hint={'center_x': 0.5, 'center_y': 0.5}, spacing=8)
        header = BoxLayout(size_hint=(1, None), height=dp(36))
        header.add_widget(Label(text='УЛУЧШЕНИЯ', font_size=20, bold=True,
                                 color=C['cyan'], halign='left'))
        self.shop_wallet = Label(text='', font_size=18, bold=True,
                                  color=C['gold'], halign='right')
        self.shop_wallet.bind(size=self.shop_wallet.setter('text_size'))
        header.add_widget(self.shop_wallet)
        box.add_widget(header)

        scroll = ScrollView(size_hint=(1, 0.82))
        self.shop_list = BoxLayout(orientation='vertical', size_hint_y=None,
                                    spacing=dp(6), padding=(dp(4), dp(4)))
        self.shop_list.bind(minimum_height=self.shop_list.setter('height'))
        scroll.add_widget(self.shop_list)
        box.add_widget(scroll)

        box.add_widget(self._mk_btn('← НАЗАД', self.show_menu,
                                     size_hint=(1, None), size=(0, 50)))
        self._refresh_shop()
        return box

    def _build_dead(self):
        box = BoxLayout(orientation='vertical', size_hint=(0.85, 0.80),
                        pos_hint={'center_x': 0.5, 'center_y': 0.5}, spacing=10)
        box.add_widget(Label(text='ВЫ ВРЕЗАЛИСЬ', font_size=26, bold=True,
                              color=C['pink'], size_hint=(1, 0.10)))
        self.dead_rec = Label(text='', font_size=14, bold=True,
                               color=C['green'], size_hint=(1, 0.05))
        box.add_widget(self.dead_rec)
        self.dead_stats = Label(text='', font_size=17, color=C['cyan'],
                                 halign='center', size_hint=(1, 0.18))
        self.dead_stats.bind(size=self.dead_stats.setter('text_size'))
        box.add_widget(self.dead_stats)

        self.revive_btn = self._mk_btn('💫 ВОЗРОДИТЬСЯ', self.revive,
                                        color=C['gold'],
                                        size_hint=(1, None), size=(0, 54))
        box.add_widget(self.revive_btn)
        box.add_widget(self._mk_btn('↻ ЕЩЁ РАЗ', self.start_game,
                                     size_hint=(1, None), size=(0, 54)))
        box.add_widget(self._mk_btn('В МЕНЮ', self.show_menu,
                                     color=C['purple'],
                                     size_hint=(1, None), size=(0, 54)))
        return box

    def _build_hud(self):
        hud = BoxLayout(orientation='horizontal', size_hint=(1, None),
                        height=dp(56), pos_hint={'top': 1},
                        spacing=dp(8), padding=(dp(10), dp(8)))
        self.hud_dist = Label(text='0 м', font_size=20, bold=True, color=C['cyan'])
        self.hud_coins = Label(text='🪙 0', font_size=20, bold=True, color=C['gold'])
        self.hud_shields = Label(text='', font_size=18, color=C['cyan'])
        hud.add_widget(self.hud_dist)
        hud.add_widget(self.hud_coins)
        hud.add_widget(self.hud_shields)
        return hud

    def _update_ui_visibility(self):
        for ui, name in ((self.menu_ui, 'menu'), (self.shop_ui, 'shop'),
                          (self.dead_ui, 'dead'), (self.hud, 'playing')):
            ui.opacity = 1 if self.state == name else 0
            ui.disabled = self.state != name

    def _refresh_menu_stats(self):
        s = self.save
        self.menu_stats.text = (f"Рекорд: {s['best']} м    "
                                 f"Монеты: {s['coins']}    "
                                 f"Забеги: {s['runs']}")

    def _refresh_shop(self):
        self.shop_wallet.text = f"🪙 {self.save['coins']}"
        self.shop_list.clear_widgets()
        for up in UPGRADES:
            lvl = self.save['up'][up['id']]
            maxed = lvl >= up['max']
            cost = 0 if maxed else up['costs'][lvl]
            ok = self.save['coins'] >= cost

            row = BoxLayout(orientation='horizontal', size_hint_y=None,
                            height=dp(78), spacing=dp(8),
                            padding=(dp(8), dp(6)))

            info = BoxLayout(orientation='vertical', size_hint=(0.72, 1))
            n = Label(text=f"{up['name']}  [{lvl}/{up['max']}]",
                      font_size=14, bold=True, color=C['cyan'],
                      halign='left', size_hint=(1, 0.5))
            n.bind(size=n.setter('text_size'))
            d = Label(text=up['desc'](lvl), font_size=11,
                      color=(1, 1, 1, 0.6), halign='left', size_hint=(1, 0.5))
            d.bind(size=d.setter('text_size'))
            info.add_widget(n)
            info.add_widget(d)
            row.add_widget(info)

            if maxed:
                btn = Button(text='MAX', size_hint=(0.28, 1),
                             background_normal='', background_color=C['green'],
                             color=(0, 0, 0, 1), bold=True, disabled=True)
            else:
                btn = Button(text=f"{cost} 🪙", size_hint=(0.28, 1),
                             background_normal='',
                             background_color=C['gold'] if ok else (0.4, 0.4, 0.4, 0.6),
                             color=(0, 0, 0, 1), bold=True, disabled=not ok)
                btn.bind(on_release=lambda *_, u=up: self._buy(u))
            row.add_widget(btn)
            self.shop_list.add_widget(row)

    # ---------- TRANSITIONS ----------
    def start_game(self):
        self.init_run()
        self.state = 'playing'
        self._update_ui_visibility()

    def show_menu(self):
        self.state = 'menu'
        self._refresh_menu_stats()
        self._update_ui_visibility()

    def show_shop(self):
        self.state = 'shop'
        self._refresh_shop()
        self._update_ui_visibility()

    def _buy(self, up):
        lvl = self.save['up'][up['id']]
        if lvl >= up['max']:
            return
        cost = up['costs'][lvl]
        if self.save['coins'] < cost:
            return
        self.save['coins'] -= cost
        self.save['up'][up['id']] += 1
        persist_save(self.save)
        self._play('buy')
        self._refresh_shop()
        self._refresh_menu_stats()

    def revive(self):
        if not self.player:
            return
        self.revive_used = True
        self.state = 'playing'
        self.invuln = 2.2
        self.shake = 0
        self.flash = 0.6
        self.obstacles = [o for o in self.obstacles if o['x'] > self.width * 0.6]
        p = self.player
        p.update(y=self.ground_y - self.stand_h, h=self.stand_h,
                  w=self.stand_w, sliding=False, vy=0,
                  on_ground=True, jumps=0, shield=1)
        self._spawn_particles(p['x'] + p['w'] / 2, p['y'] + p['h'] / 2,
                               34, C['gold'], speed=380, life=1.0)
        self._play('revive')
        self._update_ui_visibility()

    # ---------- INPUT ----------
    def on_touch_down(self, touch):
        if super().on_touch_down(touch):
            return True
        if self.state == 'playing':
            self.touch_start_y = touch.y
            self.touch_moved = False
            return True
        return False

    def on_touch_move(self, touch):
        if self.state == 'playing' and not self.touch_moved:
            if touch.y - self.touch_start_y < -dp(30):
                self.touch_moved = True
                self._start_slide()
                return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.state == 'playing' and not self.touch_moved:
            self._do_jump()
            return True
        return super().on_touch_up(touch)

    def _do_jump(self):
        p = self.player
        if not p or self.state != 'playing':
            return
        max_jumps = 2 if self.save['up']['double'] > 0 else 1
        if p['on_ground']:
            if p['sliding']:
                self._end_slide()
            p['vy'] = -self.jump_power
            p['on_ground'] = False
            p['jumps'] = 1
            self._spawn_particles(p['x'] + p['w'] / 2, self.ground_y,
                                   8, C['cyan'], angle=-math.pi / 2,
                                   spread=2.0, speed=150, life=0.4)
            self._play('jump')
        elif p['jumps'] < max_jumps:
            p['vy'] = -self.jump_power * 0.86
            p['jumps'] += 1
            self._spawn_particles(p['x'] + p['w'] / 2, p['y'] + p['h'],
                                   12, C['purple'], speed=190, life=0.4)
            self._play('jump')

    def _start_slide(self):
        p = self.player
        if not p or self.state != 'playing' or p['sliding']:
            return
        p['sliding'] = True
        p['h'], p['w'] = self.slide_h, self.slide_w
        p['slide_timer'] = 0.6
        if p['on_ground'] or p['y'] + p['h'] > self.ground_y:
            p['y'] = self.ground_y - p['h']

    def _end_slide(self):
        p = self.player
        if not p or not p['sliding']:
            return
        p['sliding'] = False
        p['h'], p['w'] = self.stand_h, self.stand_w
        if p['on_ground'] or p['y'] + p['h'] > self.ground_y:
            p['y'] = self.ground_y - p['h']

    # ---------- UPDATE ----------
    def update(self, dt):
        dt = min(dt, 0.05)
        self.bg_time += dt

        if self.state == 'playing':
            self.t += dt
            self.difficulty = clamp(self.dist / (self.height * 18), 0, 1)
            self.speed = self.base_speed * (1 + 0.85 * self.difficulty)
            self.dist += self.speed * dt
            if self.invuln > 0:
                self.invuln -= dt
            self._update_player(dt)
            self._update_obstacles(dt)
            self._update_coins(dt)
            self._update_spawning(dt)
            self._update_hud()
        else:
            self.dist += 55 * dt

        self._update_particles(dt)
        self.shake = max(0, self.shake - dt * 2.4)
        self.flash = max(0, self.flash - dt * 2.2)
        self.redraw()

    def _update_player(self, dt):
        p = self.player
        if not p:
            return
        if p['sliding']:
            p['slide_timer'] -= dt
            if p['slide_timer'] <= 0:
                self._end_slide()
        p['vy'] += self.gravity * dt
        p['y'] += p['vy'] * dt
        floor = self.ground_y - p['h']
        if p['y'] >= floor:
            p['y'] = floor
            if not p['on_ground']:
                p['on_ground'] = True
                p['jumps'] = 0
                self._spawn_particles(p['x'] + p['w'] / 2, self.ground_y,
                                       6, C['cyan'], angle=-math.pi / 2,
                                       spread=2.4, speed=130, life=0.35)
            p['vy'] = 0
        else:
            p['on_ground'] = False

    def _update_obstacles(self, dt):
        p = self.player
        if not p:
            return
        pb_x, pb_y = p['x'] + 3, p['y'] + 4
        pb_w, pb_h = p['w'] - 6, p['h'] - 7
        for o in self.obstacles[:]:
            o['x'] -= self.speed * dt
            if o['x'] + o['w'] < -120:
                self.obstacles.remove(o)
                continue
            if self.invuln > 0:
                continue
            if o['type'] == 'beam':
                ox, oy, ow, oh = o['x'], o['bottom'] - 60, o['w'], 60
            else:
                ox, oy, ow, oh = o['x'], o['y'], o['w'], o['h']
            if (pb_x < ox + ow and pb_x + 