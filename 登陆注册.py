import os

from flask import Flask, request, jsonify, render_template, redirect, url_for
import mysql.connector
from collections import defaultdict
from datetime import datetime
import jieba
from collections import Counter
import string
import re
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import pandas as pd
app = Flask(__name__)

#MySQL配置
def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="12581",
        port=3306,
        database="entertainment_news"
    )
    return conn

db_connection = get_db_connection()
cur = db_connection.cursor()
def get_related_people(query_person):
    # Create a cursor object

    # Execute the SQL query
    query = f"SELECT related_people FROM basic_info WHERE related_people LIKE '{query_person}%' OR related_people LIKE '%,{query_person}%'"
    cur.execute(query)

    # Fetch all results
    results = cur.fetchall()

    # Convert results to DataFrame
    basic_info = pd.DataFrame(results, columns=['related_people'])

    # Filter rows where 'related_people' contains {query_person}
    basic_info = basic_info[basic_info['related_people'].str.contains(query_person)]

    # Split 'related_people' column into a list of people
    basic_info['related_people'] = basic_info['related_people'].apply(lambda x: x.split(','))

    # Create a defaultdict to store occurrences of each person
    person_occurrences = defaultdict(int)
    total_occurrences = 0

    # Count occurrences of each person
    for related_people_list in basic_info['related_people']:
        if query_person in related_people_list:
            total_occurrences += 1
            for person in related_people_list:
                if person != query_person:
                    person_occurrences[person] += 1

    # Calculate conditional probabilities P(person|汪峰)
    conditional_probabilities = {person: count / total_occurrences for person, count in person_occurrences.items()}
    result_list =[]
    # Print conditional probabilities
    conditional_probabilities =dict(sorted(conditional_probabilities.items(), key=lambda item: item[1], reverse=True))
    for person, probability in conditional_probabilities.items():
        if probability < 0.1:
            continue
        result_list.append(person)
    return result_list

def filter_names(star_name,names):
    # 将人名按长度降序排列
    sorted_names = sorted(names, key=len, reverse=True)
    # 创建一个集合，用于存储被保留的人名
    filtered_names = set()
    # 遍历排序后的人名列表
    for name in sorted_names:
        # 检查当前人名是否是其他人名的前缀
        is_prefix=False
        for temp_name in sorted_names:
            if name in temp_name and len(name)<len(temp_name):
                is_prefix=True
                break


        # 如果当前人名不是其他人名的前缀，则将其加入到被保留的人名集合中
        if not is_prefix:
            filtered_names.add(name)
    filtered_results = [item for item in filtered_names if item not in star_name]
    return filtered_results

#前十热点新闻
@app.route('/heat_news', methods=['GET'])
def heat_news():
    global cur
    # 查询time表中当天reading_num前十的数据和对应的url和id
    query = 'SELECT t.title, b.url, b.id,b.cover FROM hot_time AS t JOIN basic_info AS b ON t.title = b.title ORDER BY t.reading_num DESC LIMIT 10'
    cur.execute(query)
    result = cur.fetchall()

    # 将查询结果以JSON格式返回给前端
    news_data = [{'title': item[0], 'url': item[1], 'id': item[2],'cover':item[3]} for item in result]
    return jsonify(news_data)

#前五图片轮播
@app.route('/pic', methods=['GET'])
def pic():
    global cur
    query = 'SELECT t.title, b.url, b.id, b.cover FROM hot_time AS t JOIN basic_info AS b ON t.title = b.title ORDER BY t.reading_num DESC LIMIT 5'
    cur.execute(query)
    result = cur.fetchall()
    news_data = [{'title': item[0], 'url': item[1], 'id': item[2], 'cover':item[3]} for item in result]
    return jsonify(news_data)

@app.route('/', methods=['GET'])
def home():
    return render_template('main.html')

@app.route('/nlogin', methods=['GET'])
def nlogin():
    return render_template('nlogin.html')

@app.route('/热门话题分析', methods=['GET'])
def hot_subject_page():
    return render_template('热门话题分析.html')

@app.route('/register', methods=['POST'])
def register():
    global cur
    username = request.json.get('username')
    password = request.json.get('password')

    query = 'SELECT COUNT(*) FROM user_data WHERE username = %s'
    cur.execute(query, (username,))
    result = cur.fetchone()
    existing_user_count = result[0]
    if existing_user_count > 0:
        return jsonify({'message': '用户名已存在，请选择其他用户名'}), 400
    # 将用户名和密码插入到数据库中
    cur = db_connection.cursor()
    query = 'INSERT INTO user_data (id, username, password) VALUES (NULL, %s, %s)'
    cur.execute(query, (username, password))
    db_connection.commit()

    return jsonify({'message': '注册成功'}), 200

@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username')
    password = request.json.get('password')
    query = 'SELECT * FROM user_data WHERE username = %s AND password = %s'
    cur.execute(query, (username, password))
    result = cur.fetchone()

    if result is None:
        return jsonify({'message': '用户名或密码不正确'}), 401
    else:
         return jsonify({'message': '登录成功'}), 200
#
# @app.route('/related_people', methods=['GET'])
# def related_people():
#     return
@app.route('/search',methods =['Get'])
def search_by_prefix():

    prefix = request.args.get('keyword',default=None,type=str)
    global cur
    query = """SELECT b.related_people, SUM(h.reading_num) AS total_reading_num
                  FROM basic_info AS b
                  JOIN hot_time AS h ON b.title = h.title
                  WHERE b.related_people IS NOT NULL AND b.related_people != ''
                  GROUP BY b.related_people"""
    cur.execute(query)
    result = cur.fetchall()

    # 构建人名和阅读数的字典
    people_dict = defaultdict(int)
    for item in result:
        related_people = item[0].split(',')  # 拆分多个人名
        reading_num = item[1]
        for person in related_people:
            people_dict[person.strip()] += reading_num  # 去除空格并累加阅读数

    # 获取前二十名人名及其对应的阅读数
    sorted_people = sorted(people_dict.items(), key=lambda x: x[1], reverse=True)
    known_names=[item[0]  for item in sorted_people]
    # 使用列表推导式来过滤出所有以prefix为前缀的元素
    prefixed= [s for s in known_names if s.startswith(prefix)]
    if len(prefixed)>20:
        prefixed =prefixed[:20]

    return jsonify(prefixed)
@app.route('/search_by_name',methods =['Get'])
def search_by_name():
    star_name  = request.args.get('star_name',default=None,type=str)
    sql = f"SELECT title,url,cover,brief FROM basic_info WHERE related_people LIKE '{star_name},%' or related_people like '%,{star_name}' or related_people like '%,{star_name},%' or related_people='{star_name}'"
    cur.execute(sql)
    result =cur.fetchall()
    return_reuslt = {}
    related_news = [{'title': item[0], 'cover': item[2], 'url': item[1], 'brief': item[3]} for item in result]
    return_reuslt['related_news'] = related_news
    related_people = get_related_people(star_name)
    return_reuslt['related_people']=filter_names(star_name,related_people)
    return jsonify(return_reuslt)

@app.route('/关联人物分析',methods =['Get'])
def related_people_page():
    return render_template('关联人物分析.html')

def generate_wordcloud():
    # 获取当前日期
    current_date = datetime.now()
    # 将日期转换为字符串形式
    current_date_str = current_date.strftime('%Y-%m-%d')
    filename = "static/"+current_date_str + ".jpg"
    if os.path.exists(filename):
        return

    def remove_punctuation(text):
        # 去除中文标点符号
        chinese_punctuations = "，。、；：“”‘’【】《》？！￥…（）—－"
        translator = str.maketrans('', '', string.punctuation + chinese_punctuations)
        return text.translate(translator)

    def remove_digits(text):
        return re.sub(r'\d+', '', text)

    # 从文本文件中读取停用词
    with open('data/stopwords', 'r', encoding='utf-8') as f:
        stopwords = [line.strip() for line in f.readlines()]

    # 创建数据库连接引擎
    # 假设你的MySQL服务器在本地运行，用户名是'root'，密码是'your_password'，数据库名是'entertainment_news'

    # 使用pandas的read_sql_query函数读取数据
    # 编写SQL查询来获取title列
    query = "SELECT title FROM basic_info"
    cur.execute(query)
    titles = [row[0] for row in cur.fetchall()]

    # 现在df包含了从basic_info表中读取的title列
    # 如果你只想获取title列的数据作为列表
    text = ''.join(titles)
    # 清理文本数据
    text = remove_digits(text)
    text = remove_punctuation(text)
    text = text.replace(' ', '')
    new_words = []
    with open('data/new_words.txt','r',encoding='utf-8') as f:
        new_words =[item.strip() for item in f.readlines()]
    for new_word in new_words:
        jieba.add_word(new_word)
    # 使用jieba进行分词
    word_list = list(jieba.cut(text))
    # 去除单个汉字
    word_list = [word for word in word_list if len(word) > 1]

    # 去除停用词
    filtered_word_list = [word for word in word_list if word not in stopwords]

    # 重新计算词频（可选）
    topic_word_freq = Counter(filtered_word_list)
    # print("去除停用词后的词频统计：", filtered_word_freq)

    topic_word_freq = sorted(topic_word_freq.items(), key=lambda x: x[1], reverse=True)

    # 获取词云数据
    words = [word for word, freq in topic_word_freq]

    # 获取词频数据
    word_freq = [freq for word, freq in topic_word_freq]


    # Combine words and frequencies into a dictionary
    word_freq_dict = dict(zip(words, word_freq))

    # Create a word cloud object
    wordcloud = WordCloud(font_path='C:\\Windows\\Fonts\\simsun.ttc', width=800, height=400, background_color='white',
                          colormap='rainbow').generate_from_frequencies(word_freq_dict)



    # Display the word cloud
    plt.figure(figsize=(10, 6))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    plt.savefig(filename)


if __name__ == '__main__':
    generate_wordcloud()
    app.run("0.0.0.0")