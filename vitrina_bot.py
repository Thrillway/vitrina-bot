import logging
import os
import datetime
import re
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import gspread
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")

if not BOT_TOKEN:
    raise ValueError("Bot token not set in environment variables")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
gc = gspread.service_account(filename="creds.json")
sheet = gc.open(SPREADSHEET_NAME)
products_ws = sheet.worksheet("Товары")
orders_ws = sheet.worksheet("Заказы")

user_states = {}

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_states[message.from_user.id] = {}
    brands = sorted(set(row['Бренд'] for row in products_ws.get_all_records()))
    kb = InlineKeyboardMarkup(row_width=2)
    for brand in brands:
        kb.insert(InlineKeyboardButton(brand, callback_data=f"brand:{brand}"))
    await message.answer("Привет! 👋\nВыбери бренд:", reply_markup=kb)

def get_categories(brand):
    return sorted(set(row['Категория'] for row in products_ws.get_all_records() if row['Бренд'] == brand))

def get_products(brand, category):
    return [r for r in products_ws.get_all_records() if r['Бренд'] == brand and r['Категория'] == category]

@dp.callback_query_handler(lambda c: c.data.startswith("brand:"))
async def choose_category(callback: types.CallbackQuery):
    brand = callback.data.split(":")[1]
    user_states[callback.from_user.id] = {'brand': brand}
    categories = get_categories(brand)
    kb = InlineKeyboardMarkup(row_width=2)
    for cat in categories:
        kb.insert(InlineKeyboardButton(cat, callback_data=f"category:{cat}"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back:start"))
    await callback.message.edit_text(f"Бренд: {brand}\nТеперь выбери категорию:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("category:"))
async def choose_product(callback: types.CallbackQuery):
    category = callback.data.split(":")[1]
    state = user_states.get(callback.from_user.id, {})
    brand = state.get('brand')
    if not brand:
        return await callback.message.answer("Ошибка: бренд не выбран.")
    user_states[callback.from_user.id]['category'] = category
    products = get_products(brand, category)
    kb = InlineKeyboardMarkup(row_width=1)
    for idx, product in enumerate(products):
        name = product['Название (бот)'] or product['Товар']
        kb.add(InlineKeyboardButton(name, callback_data=f"product:{idx}"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back:brand"))
    await callback.message.edit_text(f"Категория: {category}\nВыбери товар:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("product:"))
async def show_product(callback: types.CallbackQuery):
    idx = int(callback.data.split(":")[1])
    state = user_states.get(callback.from_user.id, {})
    brand = state.get('brand')
    category = state.get('category')
    products = get_products(brand, category)
    product = products[idx]
    state['product'] = product

    sizes = [s for s in ['S', 'M', 'L', 'XL'] if int(product[f'Размер {s}']) > 0]
    kb = InlineKeyboardMarkup(row_width=2)
    for s in sizes:
        kb.insert(InlineKeyboardButton(s, callback_data=f"size:{s}"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back:category"))

    caption = f"🛍️ {product['Название (бот)']}\n💰 {product['Цена за единицу']}\n📦 Остаток: {product['Общий остаток']}"
    await bot.send_photo(callback.from_user.id, photo=product['Фото (бот)'], caption=caption, reply_markup=kb)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("size:"))
async def choose_quantity(callback: types.CallbackQuery):
    size = callback.data.split(":")[1]
    state = user_states.get(callback.from_user.id, {})
    state['size'] = size
    product = state['product']
    max_qty = int(product[f'Размер {size}'])
    kb = InlineKeyboardMarkup(row_width=4)
    for i in range(1, max_qty + 1):
        kb.insert(InlineKeyboardButton(str(i), callback_data=f"qty:{i}"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="back:product"))
    await callback.message.answer(f"Выбран размер {size}. Сколько штук?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("qty:"))
async def ask_deadline(callback: types.CallbackQuery):
    qty = int(callback.data.split(":")[1])
    user_states[callback.from_user.id]['qty'] = qty
    now = datetime.datetime.now()
    kb = InlineKeyboardMarkup(row_width=3)
    for i in range(5):
        date = now + datetime.timedelta(days=i)
        kb.insert(InlineKeyboardButton(date.strftime("%d.%m"), callback_data=f"date:{date.strftime('%Y-%m-%d')}"))
    await callback.message.answer("Выбери дату получения:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("date:"))
async def choose_time(callback: types.CallbackQuery):
    date = callback.data.split(":")[1]
    user_states[callback.from_user.id]['date'] = date
    kb = InlineKeyboardMarkup(row_width=3)
    for hour in ["10:00", "12:00", "14:00", "16:00", "18:00"]:
        kb.insert(InlineKeyboardButton(hour, callback_data=f"time:{hour}"))
    await callback.message.answer("Выбери удобное время:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("time:"))
async def request_contact(callback: types.CallbackQuery):
    time = callback.data.split(":")[1]
    user_states[callback.from_user.id]['time'] = time
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("Отправить контакт ☎️", request_contact=True))
    await callback.message.answer("Оставьте контакт для оформления заказа:", reply_markup=kb)

@dp.message_handler(content_types=types.ContentType.CONTACT)
async def save_order(message: types.Message):
    state = user_states.get(message.from_user.id, {})
    product = state['product']
    size = state['size']
    qty = state['qty']
    deadline = f"{state.get('date', '')} {state.get('time', '')}"
    price = int(re.sub(r"\D", "", product['Цена за единицу'])) * qty

    orders_ws.append_row([
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        product['Название (бот)'],
        size,
        qty,
        message.contact.first_name,
        message.contact.phone_number,
        message.from_user.username or '',
        f"{price}₽",
        product['Бренд'],
        deadline
    ])
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("🔄 Сделать новый заказ", callback_data="start_over"),
        InlineKeyboardButton("❌ Завершить", callback_data="done")
    )
    await message.answer("✅ Спасибо! Ваш заказ принят.", reply_markup=types.ReplyKeyboardRemove())
    await message.answer("Что хотите сделать дальше?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "start_over")
async def start_over(callback: types.CallbackQuery):
    await start(callback.message)

@dp.callback_query_handler(lambda c: c.data == "done")
async def done(callback: types.CallbackQuery):
    await callback.message.answer("Хорошо, обращайтесь, если что-то понадобится 😊")

@dp.callback_query_handler(lambda c: c.data.startswith("back:"))
async def go_back(callback: types.CallbackQuery):
    action = callback.data.split(":")[1]
    if action == "start":
        await start(callback.message)
    elif action == "brand":
        await choose_category(callback)
    elif action == "category":
        await choose_product(callback)
    elif action == "product":
        await show_product(callback)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
