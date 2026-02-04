"""
海尔爬虫共享配置
"""

# 海尔官网基础配置
HAIER_BASE_URL = "https://www.haier.com"

# 产品分类映射
HAIER_CATEGORIES = {
    'kitchen_appliances': {
        'name': '厨房电器',
        'url': '/kitchen_appliances/',
        'description': '冰箱、洗碗机、厨电等'
    },
    'laundry': {
        'name': '洗衣机',
        'url': '/laundry/',
        'description': '洗衣机、干衣机'
    },
    'air_conditioner': {
        'name': '空调',
        'url': '/air_conditioner/',
        'description': '空调产品'
    },
    'water_heater': {
        'name': '热水器',
        'url': '/water_heater/',
        'description': '热水器产品'
    },
    'refrigerator': {
        'name': '冰箱',
        'url': '/refrigerator/',
        'description': '冰箱产品'
    }
}

# CSS 选择器配置（共享）
HAIER_SELECTORS = {
    # 列表页选择器
    'list': {
        'product_item': 'li.proitem',
        'product_title': 'a.tit1',
        'product_model': 'p.t2',
        'next_button': 'div.js_listPager a.next:not(.lose)',
        'current_page': 'div.js_listPager a.js_pageI.cur'
    },
    
    # 详情页选择器
    'detail': {
        'product_name': 'div.detail_top_content_right_centent h1[sd_key="pname"]',
        'model_number': 'div.detail_top_content_right_centent span[sd_key="modelno"]',
        'price': 'div.detail_top_content_right_centent .price em',
        'labels': 'div.detail_top_content_right_label a',
        'cover_images': 'ul.o_g img',
        'specs_tab': '#specificationTab',
        'specs_content': "div.classify_content[sd_key='specifications'] .params",
        'product_intro': '#product-intro .content-box'
    }
}


def get_category_url(category_code: str) -> str:
    """获取分类URL"""
    category = HAIER_CATEGORIES.get(category_code)
    if not category:
        raise ValueError(f"Unknown category: {category_code}")
    return HAIER_BASE_URL + category['url']


def get_category_name(category_code: str) -> str:
    """获取分类名称"""
    category = HAIER_CATEGORIES.get(category_code)
    return category['name'] if category else category_code
