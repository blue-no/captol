from __future__ import annotations
from ctypes import windll
from dataclasses import asdict
from os.path import basename, splitext, isfile
from threading import Thread
from time import sleep
import tkinter as tk
from tkinter import BOTH, DISABLED, NORMAL, CENTER, LEFT, RIGHT, TOP, BOTTOM, Y
from tkinter import ttk
from tkinter import filedialog, messagebox
from typing import Any

from ttkbootstrap import Style

from memory import AreaDB, Rectangle, Environment
from extraction import Clipper, ImageCounter, ImageBuffer
from storage import PdfConverter, PassLock


ICONFILE = 'favicon.ico'


def high_resolution() -> None:
    windll.shcore.SetProcessDpiAwareness(True)    


def noext_basename(path: str) -> str:
    return splitext(basename(path))


def get_unique_str(orgstr: str, strlist: list[str]) -> str:
    i = 0
    unistr = orgstr
    while unistr in strlist:
        i += 1
        unistr = f"{orgstr} ({i})"
    return unistr


def shorten(path: str, maxlen: int) -> str:
    path = path.replace('/', '\\')
    dirlist = path.split('\\')
    if len(dirlist) > maxlen:
        return '\\'.join(['...', dirlist[-2], dirlist[-1]])
    return path


class Application(ttk.Frame):

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root)
        self.root = root
        self.env = Environment.load()
        self.settingsframe = None
        self.setup_root()
        self.create_widgets()

    def setup_root(self) -> None:
        self.root.iconbitmap(ICONFILE)
        self.root = Style("darkly").master
        self.root.title("Captol dev")
        self.root.attributes('-topmost', True)
        self.root.resizable(False, False)
        self.root.geometry("460x530-0+0")

    def create_widgets(self) -> None:
        note = self.note = ttk.Notebook(self)
        note.root = self
        note.place(x=0, y=10, relwidth=1, relheight=1)
        note.add(StoreFrame(note, parent=self, env=self.env), text="Store")
        note.add(ExtractFrame(note, parent=self, env=self.env), text="Extract")
        ttk.Button(
            self, text="Settings", style='secondary.Outline.TButton',
            command=self.on_settings_clicked).place(x=360, y=4, width=95)
        self.pack(fill=BOTH, expand=True)

    def on_settings_clicked(self) -> None:
        if self.settingsframe is None or not self.settingsframe.root.winfo_exists():
            self.settingsframe = SettingsFrame(parent=self, env=self.env)

    def resize(self, geometry: str) -> None:
        self.root.geometry(geometry)

    def enable_secondtab(self) -> None:
        self.note.tab(1, state=NORMAL)

    def disable_secondtab(self) -> None:
        self.note.tab(1, state=DISABLED)


class ExtractFrame(ttk.Frame):

    def __init__(self, root: tk.Tk, parent: Application,
                 env: Environment) -> None:
        super().__init__(root)
        self.root = root
        self.parent = parent
        self.env = env
        self.prevname = None
        self.var_folder = tk.StringVar()
        var_images_total = self.var_images_total = tk.IntVar()
        images_today = self.images_today = tk.IntVar()
        self.var_listitems = tk.StringVar()
        self.var_clipmode = tk.IntVar(value=2)
        areadb = self.areadb = AreaDB(env)
        self.counter = ImageCounter('png', var_images_total, images_today)
        self.clipper = Clipper()
        self.transparent = TransparentFrame(parent=root)

        self.create_widgets()
        self._reset_folder_info(env.default_folder)
        self._reset_clip_areas(areadb.namelist)

    def create_widgets(self) -> None:
        frame1 = self.frame1 = ttk.Frame(self, height=350)
        frame1.pack(fill=BOTH, expand=True)

        ttk.LabelFrame(frame1, text="Save folder").place(
            x=10, y=10, width=435, height=170)
        ttk.Button(frame1, text="📁", style='secondary.Outline.TButton',
                   command=self.on_folder_clicked).place(x=30, y=50, width=45)
        ttk.Entry(frame1, textvariable=self.var_folder, state='readonly').place(
            x=80, y=52, width=345)
        ttk.Label(frame1, text="Past images:").place(x=30, y=100)
        ttk.Label(frame1, textvariable=self.var_images_total, anchor=CENTER).place(
            x=200, y=100, width=200)
        ttk.Label(frame1, text="Today's images:").place(x=30, y=140)
        ttk.Label(frame1, textvariable=self.images_today, anchor=CENTER).place(
            x=200, y=140, width=200)

        ttk.LabelFrame(frame1, text="Clip area").place(
            x=10, y=190, width=435, height=220)
        lb_areas = self.lb_areas = tk.Listbox(
            frame1, listvariable=self.var_listitems)
        lb_areas.place(x=30, y=230, height=160)
        ttk.Button(frame1, text="+", command=self.on_plus_clicked).place(
            x=275, y=230, width=70)
        ttk.Button(frame1, text="−", command=self.on_minus_clicked).place(
            x=355, y=230, width=70)
        ttk.Button(frame1, text="Edit", command=self.on_edit_clicked).place(
            x=275, y=280, width=150)
        ttk.Button(
            frame1, text="Launch", style='warning.TButton',
            command=self.on_launch_clicked).place(x=275, y=350, width=150)
        lb_areas.bind('<<ListboxSelect>>', self.on_area_selected)

        frame2 = self.frame2 = ttk.Frame(self)
        frame2.pack(fill=BOTH, expand=True)
        clipframe = self.clipframe = ClipFrame(
            frame2, parent=self, env=self.env, clipper=self.clipper,
            counter=self.counter)
        clipframe.pack(fill=BOTH, expand=True)
        self.pack()

    def on_folder_clicked(self) -> None:
        folder = filedialog.askdirectory(title="Open folder")
        if folder:
            self._reset_folder_info(folder)

    def on_area_selected(self, event: Any) -> None:
        name = self._get_lbselection()
        rect = self.areadb.get(name)
        if name != self.prevname:
            self.transparent.resize(**asdict(rect))
            self.transparent.preview()
            self.prevname = name
        else:
            self.transparent.hide()
            self.prevname = None

    def on_plus_clicked(self) -> None:
        self.transparent.hide()
        EditorDialog(parent=self, areadb=self.areadb)

    def on_minus_clicked(self) -> None:
        name = self._get_lbselection()
        if name is not None:
            if messagebox.askyesno(
                "Delete Item",
                "Are you sure to delete this item?"
                "\n(The operation cannot be undone.)"):
                self.areadb.delete(name)
                self.update_listitems()
                self.transparent.hide()
            if self.clipframe.is_activated_byname(name):
                self.clipframe.init_vars()
                self.clipframe.block_widgets()

    def on_edit_clicked(self) -> None:
        name = self._get_lbselection()
        if name is not None:
            self.transparent.hide()
            EditorDialog(parent=self, areadb=self.areadb, name=name)
        
    def on_launch_clicked(self) -> None:
        name = self._get_lbselection()
        if name is not None:
            rect = self.areadb.get(name)
            self.clipframe.register_cliparea(name, rect)
            self.clipframe.release_widgets()

    def shrink(self) -> None:
        self.frame1.pack_forget()
        self.parent.disable_secondtab()
        self.parent.resize("460x110")

    def extend(self) -> None:
        self.frame2.pack_forget()
        self.frame1.pack(fill=BOTH, expand=True)
        self.frame2.pack(fill=BOTH, expand=True)
        self.parent.enable_secondtab()
        self.parent.resize("460x530")

    def block_widgets(self) -> None:
        for widget in self.frame1.winfo_children():
            try:
                widget['state'] = DISABLED
            except tk.TclError:
                pass
    
    def release_widgets(self) -> None:
        for widget in self.frame1.winfo_children():
            try:
                widget['state'] = NORMAL
            except tk.TclError:
                pass
    
    def update_listitems(self, activate_name : str = None) -> None:
        self._reset_clip_areas(self.areadb.namelist)
        if activate_name is not None:
            self._select_lbitem(activate_name)

    def update_clipinfo(self, oldname: str, newname: str,
                        newrect: Rectangle) -> None:
        if self.clipframe.is_activated_byname(oldname):
            self.clipframe.register_cliparea(newname, newrect)
            
    def _reset_folder_info(self, folder: str) -> None:
        self.var_folder.set(shorten(folder, maxlen=4))
        self.counter.change_dir(folder)
        self.counter.initialize_count()
    
    def _reset_clip_areas(self, keys: list) -> None:
        self.var_listitems.set(keys)

    def _select_lbitem(self, name: str) -> None:
        idx = self.areadb.namelist.index(name)
        self.lb_areas.select_set(idx)
        self.lb_areas.see(idx)
    
    def _get_lbselection(self) -> str | None:
        idx = self.lb_areas.curselection()
        if len(idx) > 1:
            idx = idx[-1]
        if idx != ():
            return self.lb_areas.get(idx)
        return None


class ClipFrame(ttk.Frame):

    def __init__(self, root: tk.Tk, parent: ExtractFrame, env: Environment,
                 clipper: Clipper, counter: ImageCounter) -> None:
        super().__init__(root)
        self.parent = parent
        self.env = env
        self.clipper = clipper
        self.counter = counter
        self.thread = None
        self.thread_alive = False
        self.var_clipmode = tk.IntVar()
        self.var_areaname = tk.StringVar()
        self.imbuffer = ImageBuffer(env)
        self.transparent = TransparentFrame(parent=self)

        self.create_widgets()
        self.block_widgets()
        self.init_vars()

    def create_widgets(self) -> None:
        ttk.Button(self, text="📸", style='warning.TButton',
                   command=self.on_camera_clicked).place(x=10, y=10, width=60)
        ttk.Label(self, text="[                   ]", anchor=CENTER).place(
            x=80, y=15, width=130)
        ttk.Label(self, textvariable=self.var_areaname, anchor=CENTER).place(
            x=90, y=15, width=110)
        ttk.Radiobutton(
            self, text="Manual", value=1, variable=self.var_clipmode,
            command=self.on_manual_clicked).place(x=225, y=18)
        ttk.Radiobutton(
            self, text="Auto", value=2, variable=self.var_clipmode,
            style='danger.TRadiobutton',command=self.on_auto_clicked).place(
                x=320, y=18)
        fold_button = self.fold_button = ttk.Button(
            self, text="▲", style='secondary.Outline.TButton',
            command=self.on_fold_clicked)
        fold_button.place(x=400, y=10, width=45)

    def on_camera_clicked(self) -> None:
        if self.clipper.area is None:
            return
        self._normal_save()

    def on_fold_clicked(self) -> None:
        self.parent.shrink()
        self.fold_button['text'] = "▼"
        self.fold_button['command'] = self.on_unfold_clicked

    def on_unfold_clicked(self) -> None:
        self.parent.extend()
        self.fold_button['text'] = "▲"
        self.fold_button['command'] = self.on_fold_clicked

    def on_manual_clicked(self) -> None:
        if self.thread_alive:
            self._end_autoclip()
            messagebox.showinfo("Autoclip", "Autoclip stopped.")
            self.parent.release_widgets()

    def on_auto_clicked(self) -> None:
        if messagebox.askyesno(
            "Autoclip", "Do you want to enable Autoclip?", master=self):
            self.parent.block_widgets()
            self._start_autoclip()
        else:
            self.var_clipmode.set(1)

    def register_cliparea(self, name: str, rect: Rectangle) -> None:
        self.clipper.register(rect)
        self.var_areaname.set(name)
        self.transparent.resize(**asdict(rect))
    
    def block_widgets(self) -> None:
        for widget in self.winfo_children():
            try:
                widget['state'] = DISABLED
            except tk.TclError:
                pass
    
    def release_widgets(self) -> None:
        for widget in self.winfo_children():
            try:
                widget['state'] = NORMAL
            except tk.TclError:
                pass

    def init_vars(self) -> None:
        self.var_clipmode.set(1)
        self.var_areaname.set("------")

    def is_activated_byname(self, name: str) -> bool:
        if self.fold_button['state'] == DISABLED:
            return False
        if self.var_areaname.get() == name:
            return True
        return False

    def _start_autoclip(self) -> None:
        def _autoclip():
            while self.thread_alive:
                if self.env.enalbe_active_image_saver:
                    self._active_save()
                else:
                    self._nodup_save()
                sleep(self.env.autoclip_interval)

        self.thread_alive = True
        thread = self.thread = Thread(target=_autoclip)
        thread.start()
    
    def _end_autoclip(self) -> None:
        if self.thread is not None:
            self.thread_alive = False
            self.thread.join()

    def _normal_save(self) -> None:
        self.transparent.hide_all()
        image = self.clipper.clip()
        self.imbuffer.hold(image)
        name = self.counter.next_savepath()
        self.imbuffer.save(name)
        self.transparent.flash()
        self.counter.up(1)

    def _nodup_save(self) -> None:
        self.transparent.hide_all()
        image = self.clipper.clip()
        self.imbuffer.hold(image)

        if self.imbuffer.compare_similarity(past_step=1):
            self.imbuffer.release()
        else:
            name = self.counter.next_savepath()
            self.imbuffer.save(name)
            self.transparent.flash()
            self.counter.up(1)

    def _active_save(self) -> None:
        self.transparent.hide_all()
        image = self.clipper.clip()
        self.imbuffer.hold(image)

        if self.imbuffer.compare_similarity(past_step=1):
            self.imbuffer.release()
        elif self.imbuffer.compare_similarity(past_step=2):
            self.imbuffer.delete(past_step=2)
            self.imbuffer.delete(past_step=1)
            name = self.counter.next_savepath()
            self.imbuffer.save(name)
            self.transparent.flash()
            self.counter.down(1)
        else:
            name = self.counter.next_savepath()
            self.imbuffer.save(name)
            self.transparent.flash()
            self.counter.up(1)


class EditorDialog(ttk.Frame):

    def __init__(self, parent: ExtractFrame, areadb: AreaDB,
                 name: str = None) -> None:
        root = self.root = tk.Toplevel(parent)
        super().__init__(root)
        self.parent = parent
        self.areadb = areadb
        self.init_name = name
        self.name = tk.StringVar()
        self.x = tk.IntVar()
        self.y = tk.IntVar()
        self.w = tk.IntVar()
        self.h = tk.IntVar()
        self.transparent = TransparentFrame(self)

        self.setup_root()
        self.create_widgets()
        self.set_initvalue()
    
    def setup_root(self) -> None:
        self.root.iconbitmap(ICONFILE)
        self.root.resizable(False, False)
        self.root.title("Edit")
        self.root.attributes('-topmost', True)
        self.root.geometry("460x250")
        self.root.protocol('WM_DELETE_WINDOW', self.on_cancel)
        self.root.grab_set()

    def create_widgets(self) -> None:
        ttk.Label(self, text="Area name: ").place(x=10, y=20)
        ttk.Entry(self, textvariable=self.name).place(x=130, y=20, width=320)
        ttk.LabelFrame(self, text="Area").place(
            x=10, y=60, width=440, height=130)
        ttk.Button(
            self, text="Direct\nDraw",
            command=self.on_direct_draw).place(x=30, y=95, width=90, height=80)
        ttk.Label(self, text="x:").place(x=150, y=95)
        ttk.Spinbox(self, textvariable=self.x, from_=0, to=9999).place(
            x=180, y=95, width=80)
        ttk.Label(self, text="width:").place(x=280, y=95)
        ttk.Spinbox(self, textvariable=self.w, from_=0, to=9999).place(
            x=350, y=95, width=80)
        ttk.Label(self, text="y:").place(x=150, y=140)
        ttk.Spinbox(self, textvariable=self.y, from_=0, to=9999).place(
            x=180, y=140, width=80)
        ttk.Label(self, text="height:").place(x=280, y=140)
        ttk.Spinbox(self, textvariable=self.h, from_=0, to=9999).place(
            x=350, y=140, width=80)
        ttk.Button(
            self, text="OK", command=self.on_ok,
            style='secondary.TButton').place(x=40, y=200, width=160)
        ttk.Button(
            self, text="Cancel", command=self.on_cancel,
            style='secondary.Outline.TButton').place(x=260, y=200, width=160)
        self.pack(fill=BOTH, expand=True)

    def set_initvalue(self) -> None:
        name = self.init_name
        if self.areadb.has_name(name):
            x, y, w, h = asdict(self.areadb.get(name)).values()
        else:
            x, y, w, h = 100, 200, 400, 300
            name = get_unique_str("New", self.areadb.namelist)

        self.x.set(x)
        self.y.set(y)
        self.w.set(w)
        self.h.set(h)
        self.name.set(name)
        self.transparent.resize(x, y, w, h)
        self.transparent.preview()

    def on_direct_draw(self) -> None:
        Drawer(self, self.transparent, self.x, self.y, self.w, self.h)
        self.transparent.hide()

    def on_ok(self) -> None:
        name = self.name.get()
        x, y, w, h = self.x.get(), self.y.get(), self.w.get(), self.h.get()
        if not self._validate(name, x, y, w, h):
            return
        
        if name != self.init_name:
            if self.areadb.has_name(name):
                if not messagebox.askyesno(
                    "Editor",
                    "The same name already exists."
                    "Are you sure to overwrite it?"):
                    return
            if self.init_name is not None:
                self.areadb.delete(self.init_name)
        
        rect = Rectangle(x, y, w, h)
        self.areadb.write(name, rect)
        self.areadb.save()
        self.parent.update_listitems(activate_name=name)
        self.parent.update_clipinfo(self.init_name, name, rect)
        self.parent.transparent.resize(x, y, w, h)
        self.parent.transparent.preview()
        self.root.destroy()

    def on_cancel(self) -> None:
        if messagebox.askyesno(
            "Edior", "Do you want to leave? \n(Edits are not saved.)"):
            self.transparent.hide()
            self.parent.transparent.preview()
            self.root.destroy()

    def block_widgets(self) -> None:
        for widget in self.winfo_children():
            try:
                widget['state'] = DISABLED
            except tk.TclError:
                pass
    
    def release_widgets(self) -> None:
        for widget in self.winfo_children():
            try:
                widget['state'] = NORMAL
            except tk.TclError:
                pass

    def _validate(self, name: str, x: int, y: int, w: int, h: int) -> bool:
        if name == "":
            messagebox.showerror("Invalid Input", "Area name cannot be blank.")
            return False
        if min(x, y, w, h) < 0:
            messagebox.showerror(
                "Invalid Input", "Minous value is not allowed.")
            return False
        return True


class Drawer(ttk.Frame):

    def __init__(self, parent: EditorDialog, transparent: TransparentFrame,
                 var_x: tk.IntVar, var_y: tk.IntVar, var_w: tk.IntVar,
                 var_h: tk.IntVar) -> None:
        root = self.root = tk.Toplevel(parent)
        super().__init__(root)
        self.root = root
        self.parent = parent
        self.var_x = var_x
        self.var_y = var_y
        self.var_w = var_w
        self.var_h = var_h
        self.start_x = None
        self.start_y = None
        self.setup_root()
        self.create_widgets()  # iconifyは座標がずれる
        self.transparent = transparent
        self.parent.block_widgets()

    def setup_root(self) -> None:
        self.root.attributes('-fullscreen', True)
        self.root.resizable(False, False)
        self.root.attributes('-alpha', 0.1)
        self.root.overrideredirect(True)

    def create_widgets(self) -> None:
        self.canvas = canvas = tk.Canvas(self, bg='cyan', highlightthickness=0)
        canvas.pack(fill=BOTH, expand=True)
        canvas.bind('<ButtonPress-1>', self.on_drag_start)
        canvas.bind('<B1-Motion>', self.on_moving)
        canvas.bind('<ButtonRelease>', self.on_drag_end)
        self.pack(fill=BOTH, expand=True)

    def on_drag_start(self, event) -> None:
        self.start_x = event.x
        self.start_y = event.y
        self.transparent.resize(0, 0, 0, 0)
        self.transparent.preview()

    def on_moving(self, event) -> None:
        sx, sy, cx, cy = self.start_x, self.start_y, event.x, event.y
        x, y, w, h = min(sx, cx), min(sy, cy), abs(sx-cx), abs(sy-cy)
        self.transparent.resize(x, y, w, h)

    def on_drag_end(self, event) -> None:
        sx, sy, cx, cy = self.start_x, self.start_y, event.x, event.y
        self.var_x.set(min(sx, cx))
        self.var_y.set(min(sy, cy))
        self.var_w.set(abs(sx-cx))
        self.var_h.set(abs(sy-cy))
        self.parent.release_widgets()
        self.root.destroy()


class TransparentFrame(tk.Frame):
    roots: list[tk.Tk] = list()

    def __init__(self, parent: Any) -> None:
        root = self.root = tk.Toplevel(parent)
        super().__init__(root, bg='white')
        self.parent = parent
        self.marks = None
        self.prev_name = None
        self.setup_root()
        self.create_widgets()
        self.hide()

    def setup_root(self) -> None:
        # self.root.resizable(False, False)
        self.root.attributes('-alpha', 0.3)
        self.root.overrideredirect(True)
        TransparentFrame.roots.append(self.root)

    def create_widgets(self) -> None:
        self.marks = frame = tk.Frame(self, bg='white')
        size_v = 30
        size_h = int(size_v * 1.6)
        size_c = int(size_v * 0.4)
        tk.Label(
            frame, text='◀◁', font=('', size_h, 'bold'),
            fg='black', bg='white').pack(side=LEFT, fill=Y)
        tk.Label(
            frame, text='▷▶', font=('', size_h, 'bold'),
            fg='black', bg='white').pack(side=RIGHT, fill=Y)
        tk.Label(
            frame, text='▲\n△', font=('', size_v),
            fg='black', bg='white').pack(side=TOP)
        tk.Label(
            frame, text='▽\n▼', font=('', size_v),
            fg='black', bg='white').pack(side=BOTTOM)
        tk.Label(
            frame, text='＋', font=('', size_c),
            fg='black', bg='white').pack(expand=True)
        self.pack(fill=BOTH, expand=True)

    def hide(self) -> None:
        self.root.withdraw()
    
    def hide_all(self) -> None:
        for root in TransparentFrame.roots:
            try:
                root.withdraw()
            except tk.TclError:
                pass

    def preview(self) -> None:
        self.marks.pack(fill=BOTH, expand=True)
        self.root.lift()
        self.parent.root.lift()
        self.root.deiconify()

    def flash(self) -> None:
        self.root.withdraw()
        self.marks.pack_forget()
        self.root.lift()
        self.root.deiconify()
        self.root.after(80, self.root.withdraw)

    def resize(self, x: int, y: int, w: int, h:int) -> None:
        getmetry = f'{w}x{h}+{x}+{y}'
        self.root.geometry(getmetry)


class StoreFrame(ttk.Frame):

    def __init__(self, root: tk.Tk, parent: Any, env: Environment) -> None:
        super().__init__(root)
        self.var_images_total = tk.IntVar()
        self.var_imagename_from = tk.StringVar()
        self.var_imagename_to = tk.StringVar()
        self.image_paths = None
        self.var_pdf_path = tk.StringVar()
        self.var_pwd1 = tk.StringVar()
        self.var_pwd2 = tk.StringVar()
        self.converter = PdfConverter(env)
        self.passlock = PassLock(env)

        self.create_widgets()
        self.init_vars_conversion()
        self.init_vars_protection()

    def create_widgets(self) -> None:
        ttk.LabelFrame(self, text="PDF conversion").place(
            x=10, y=10, width=435, height=130)
        ttk.Button(
            self, text="📁", style='secondary.Outline.TButton',
            command=self.on_imagefolder_clicked).place(x=30, y=50, width=45)
        ttk.Entry(
            self, textvariable=self.var_imagename_from,
            state='readonly').place(x=80, y=52, width=160)
        ttk.Label(self, text="–").place(x=246, y=52)
        ttk.Entry(
            self, textvariable=self.var_imagename_to,
            state='readonly').place(x=267, y=52, width=160)
        ttk.Label(self, text="Total images:").place(x=30, y=100)
        ttk.Label(self, textvariable=self.var_images_total, anchor=CENTER).place(
            x=200, y=100, width=200)
        ttk.Button(
            self, text="Convert", command=self.on_convert_clicked).place(x=150, y=150, width=160)
        ttk.LabelFrame(self, text="Password protection").place(
            x=10, y=220, width=435, height=200)
        ttk.Button(
            self, text="📁", style='secondary.Outline.TButton',
            command=self.on_pdffolder_clicked).place(x=30, y=260, width=45)
        ttk.Entry(
            self, textvariable=self.var_pdf_path, state='readonly').place(x=80, y=262, width=345)
        ttk.Label(self, text="Password:").place(x=30, y=320)
        ent_pwd1 = self.ent_pwd1 = ttk.Entry(self)
        ent_pwd1.place(x=145, y=317, width=280)
        ttk.Label(self, text="Again:").place(x=30, y=370)
        ent_pwd2 = self.ent_pwd2 = ttk.Entry(self)
        ent_pwd2.place(x=145, y=366, width=280)
        ttk.Button(self, text="Lock").place(x=150, y=430, width=160)
        self.pack()
    
    def init_vars_conversion(self) -> None:
        self.var_imagename_from.set("")
        self.var_imagename_to.set("")
        self.var_images_total.set(0)
        self.image_paths = None

    def init_vars_protection(self) -> None:
        self.var_pdf_path.set("")
        self.var_pwd1.set("")
        self.var_pwd2.set("")
        self.ent_pwd1['show'] = "●"
        self.ent_pwd2['state'] = DISABLED
    
    def on_imagefolder_clicked(self) -> None:
        images = filedialog.askopenfilenames(title="Select Images", filetypes=[('png', '*.png')])
        if images:
            self.var_imagename_from.set(noext_basename(images[0]))
            if len(images) > 1:
                self.var_imagename_to.set(noext_basename(images[-1]))
        else:
            self.var_imagename_to.set("")
            self.var_images_total.set(len(images))
            self.image_paths = images
    
    def on_convert_clicked(self) -> None:
        if self.image_paths is None:
            return
        savepath = filedialog.asksaveasfilename(title="Save as", filetypes=[('pdf', '*.pdf')])
        if not savepath:
            return
        if not savepath.endswith(('.pdf', '.PDF')):
            savepath += '.pdf'
        if isfile(savepath):
            if not messagebox.askyesno(
                "Save pdf",
                "A pdf file with the same name already exists."
                "\nAre you sure to overwrite it?"):
                return
        self.converter.save_as_pdf(self.image_paths, savepath)
        self.init_vars_conversion()

    def on_pdffolder_clicked(self):
        pdf = filedialog.askopenfilename(title="Select PDF", filetypes=[('pdf', '*.pdf')])
        if not pdf:
            return
        
        self.var_pdf_path.set(shorten(pdf, maxlen=2))
        # if self.passlock.is_encrypted(pdf):
        #     self.


class SettingsFrame(ttk.Frame):
    
    def __init__(self, parent: Application, env: Environment) -> None:
        root = self.root = tk.Toplevel(parent)
        super().__init__(root)
        self.parent = parent
        self.env = env
        self.var_default_folder = tk.StringVar()
        self.var_enable_active_image_saver = tk.BooleanVar()
        self.var_enable_pdf_compression = tk.BooleanVar()
        self.var_compression_ratio = tk.IntVar()
        self.var_password_security_level = tk.IntVar()
        self.setup_root()
        self.create_widgets()
        self.init_vars()

    def setup_root(self) -> None:
        self.root.iconbitmap(ICONFILE)
        # self.root.resizable(False, False)
        self.root.title("Environmental Settings")
        self.root.attributes('-topmost', True)
        self.root.geometry('460x320')

    def create_widgets(self) -> None:
        ttk.Label(self, text="Default folder").place(x=20, y=20)
        ttk.Entry(self, textvariable=self.var_default_folder).place(
            x=20, y=50, width=420)
        ttk.Label(self, text="Enable Active Image Saver").place(x=20, y=100)
        ttk.Checkbutton(
            self,
            variable=self.var_enable_active_image_saver).place(x=400, y=100)
        ttk.Label(self, text="Enable pdf compression").place(x=20, y=140)
        ttk.Checkbutton(
            self, variable=self.var_enable_pdf_compression,
            command=self.on_enable_comp).place(x=400, y=140)
        ttk.Label(self, text="Compression ratio").place(x=20, y=180)
        spb_ratio = self.spb_ratio = ttk.Spinbox(
            self, textvariable=self.var_compression_ratio, from_=60, to=90)
        spb_ratio.place(x=380, y=180, width=60)
        ttk.Label(self, text="Password security level").place(x=20, y=220)
        ttk.Spinbox(
            self, textvariable=self.var_password_security_level,
            from_=1, to=3).place(x=380, y=220, width=60)
        ttk.Button(
            self, text="OK", command=self.on_ok,
            style='secondary.TButton').place(x=40, y=270, width=160)
        ttk.Button(
            self, text="Cancel", command=self.on_cancel,
            style='secondary.Outline.TButton').place(x=260, y=270, width=160)
        self.pack(fill=BOTH, expand=True)
    
    def init_vars(self) -> None:
        env = self.env
        self.var_default_folder.set(env.default_folder)
        self.var_enable_active_image_saver.set(env.enalbe_active_image_saver)
        self.var_enable_pdf_compression.set(env.enable_pdf_compression)
        self.var_compression_ratio.set(env.compression_ratio)
        self.var_password_security_level.set(env.password_security_level)

    def on_enable_comp(self) -> None:
        if not self.var_enable_pdf_compression.get():
            self.spb_ratio['state'] = DISABLED
        else:
            self.spb_ratio['state'] = NORMAL
    
    def on_ok(self) -> None:
        env = self.env
        env.default_folder = self.var_default_folder.get()
        env.enalbe_active_image_saver = self.var_enable_active_image_saver.get()
        env.enable_pdf_compression = self.var_enable_pdf_compression.get()
        env.compression_ratio = self.var_compression_ratio.get()
        env.password_security_level = self.var_password_security_level.get()
        self.env = env
        env.save()
        self.root.destroy()

    def on_cancel(self) -> None:
        if messagebox.askyesno(
            "Settings", "Do you want to leave? \n(Edits are not saved.)"):
            self.root.destroy()





if __name__ == '__main__':
    high_resolution()
    root = tk.Tk()
    Application(root)
    root.mainloop()
