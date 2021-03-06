# -*- coding: utf-8 -*-
import scrapy
import json
import re
from yiche_spider import items


class CarSpider(scrapy.Spider):
    name = 'car'
    allowed_domains = ['bitauto.com']
    start_urls = ['http://api.car.bitauto.com/CarInfo/getlefttreejson.ashx?tagtype=chexing&pagetype=&objid=']
    external_urls = {
        'brand_logo_img_path': 'http://image.bitautoimg.com/bt/car/default/images/logo/masterbrand/png/100/m_%s_100.png',
        'car_list': 'http://api.car.bitauto.com/CarInfo/MasterBrandToSerialNew.aspx?type=5&pid=%s&rt=serial&serias=m&key=serial_%s_5_m&include=1',
        'car_version_list': 'http://api.car.bitauto.com/CarInfo/MasterBrandToSerialNew.aspx?type=5&pid=%s&rt=cartype&serias=m&key=cartype_%s_5_m&include=1',
        'car_version_attr': 'http://car.bitauto.com/asidunmadingdb11/m%s/',
    }
    custom_settings = {}

    def parse(self, response):
        priority = 10000
        ignore_data = int(response.headers['IGNORE-DATA']) if 'IGNORE-DATA' in response.headers else 0
        result = re.findall(r'type:\"(.*?)\",id:(.*?),name:\"(.*?)\",url:\"(.*?)\",cur', response.body)

        for brand in result:
            third_id = brand[1]
            name = brand[2].decode('utf-8')
            logo_image = self.external_urls['brand_logo_img_path'] % third_id

            if not ignore_data:
                # 保存品牌入库
                item = items.BrandItem()
                item['third_id'] = third_id
                item['name'] = name
                item['remote_logo'] = logo_image
                yield item

            print u'[品牌] ' + ('' if ignore_data else '+ ') + name

            priority -= 1
            url = self.external_urls['car_list'] % (third_id, third_id)
            yield scrapy.Request(url, callback=self.parse_car_data, meta={'brand_name': name, 'check_data': 1}, priority=priority)

    # 解析车型json串
    def parse_car_data(self, response):
        priority = 9000
        ignore_data = int(response.headers['IGNORE-DATA']) if 'IGNORE-DATA' in response.headers else 0
        data = response.body
        dict_data = json.loads(data[data.find('{'):], strict=False)
        for k in dict_data:
            third_id = dict_data[k]['id']
            name = dict_data[k]['name']
            if not ignore_data:
                # 保存品牌车型入库
                item = items.CarItem()
                item['third_id'] = third_id
                item['name'] = name
                item['show_name'] = dict_data[k]['showName']
                item['en_name'] = dict_data[k]['urlSpell']
                item['brand_third_id'] = dict_data[k]['pid']
                item['factory_third_id'] = dict_data[k]['goid']
                item['factory_name'] = dict_data[k]['goname']
                item['sale_state'] = dict_data[k]['csSale']
                yield item

            print u'[车型] ' + ('' if ignore_data else '+ ') + response.meta['brand_name'] + ' ' + name

            priority -= 1
            url = self.external_urls['car_version_list'] % (third_id, third_id)
            yield scrapy.Request(url, callback=self.parse_car_version_data, meta={'brand_name': response.meta['brand_name'], 'car_name': name, 'check_data': 1}, priority=priority)

    # 解析车款json串
    def parse_car_version_data(self, response):
        ignore_data = int(response.headers['IGNORE-DATA']) if 'IGNORE-DATA' in response.headers else 0
        data = response.body
        dict_data = json.loads(data[data.find('{'):], strict=False)
        for k in dict_data:
            third_id = dict_data[k]['id']
            name = dict_data[k]['name']

            car_version_full_name = response.meta['brand_name'] + ' ' + response.meta['car_name'] + ' ' + name
            print u'[车款] ' + ('' if ignore_data else '+ ') + car_version_full_name

            if not ignore_data:
                # 保存车款入库
                item = items.CarVersionItem()
                item['car_third_id'] = dict_data[k]['pid']
                item['third_id'] = third_id
                item['name'] = dict_data[k]['name']
                item['refer_price'] = dict_data[k]['referprice']
                item['sale_state'] = dict_data[k]['salestate']
                item['year_type'] = dict_data[k]['goname']
                item['tt'] = dict_data[k]['tt']
                yield item

                url = self.external_urls['car_version_attr'] % third_id
                yield scrapy.Request(url, callback=self.parse_car_version_attr_page, meta={'car_version_id': third_id, 'car_version_full_name': car_version_full_name})

    # 解析车款配置页面
    def parse_car_version_attr_page(self, response):
        data_dict = {}
        params_dict = self.get_params_dict()

        attr_selector = response.xpath('//div[contains(@class, "config-section")]//div[contains(@class, "special-layout-18")]')
        items_text_selector = attr_selector.xpath('.//td/span[@class="title"]')
        for item_selector in items_text_selector:
            item_text = (item_selector.xpath('text()').extract()[0])[:-1]

            if not item_text:
                continue

            item_value_selector = item_selector.xpath('../following-sibling::td[1]')
            # 车身颜色字段解析
            if item_text == u'车身颜色':
                color_items_selector = item_value_selector.xpath('.//div[@class="focus-color-warp"]//li/a')
                color_items = []
                for color in color_items_selector:
                    color_items.append(color.xpath('@title').extract()[0]+':'+(color.xpath('./span/@style').extract()[0])[-7:])
                item_value = ','.join(color_items)
            else:
                item_value = item_value_selector.xpath('./span[@class="info"]/text()').extract()
                if not item_value:
                    item_value = ','.join(item_value_selector.xpath('.//div[@class="l"]/text()').extract())

            for k, v in params_dict.items():
                if item_text == v.decode('utf-8'):
                    group_k = k.split('.')[0]
                    item_k = k.split('.')[1]
                    if not data_dict.has_key(group_k):
                        data_dict[group_k] = {}
                    data_dict[group_k][item_k] = self.get_value(item_value)

        # 保存车款配置入库
        item = items.CarVersionAttrItem()
        item['car_version_third_id'] = response.meta['car_version_id']
        item['content'] = json.dumps(data_dict)
        yield item

        print u'[车款配置] ' + response.meta['car_version_full_name']

    @staticmethod
    def get_params_dict():
        params_dict = {
            'base.price': '厂商指导价',
            'base.warrantypolicy': '保修政策',
            'base.maxspeed': '最高车速',
            'base.comfuelconsumption': '混合工况油耗',
            'base.officialaccelerationtime100': '0-100km/h加速时间',
            # 车身
            'body.len': '长',
            'body.width': '宽',
            'body.height': '高',
            'body.wheelbase': '轴距',
            'body.weight': '整备质量',
            'body.seatnumber': '座位数',
            'body.luggagevolume': '行李厢容积',
            'body.fueltankcapacity': '油箱容积',
            'body.color': '车身颜色',
            'body.inductionluggage': '电动行李厢',
            'body.roofluggagerack': '车顶行李箱架',
            'body.sportpackage': '运动外观套件',
            # 动力
            'engine.displacementml': '排气量',
            'engine.displacement': '排量',
            'engine.maxpower': '最大功率',
            'engine.maxhorsepower': '最大马力',
            'engine.maxpowerspeed': '最大功率转速',
            'engine.maxtorque': '最大扭矩',
            'engine.maxtorquespeed': '最大扭矩转速',
            'engine.cylinderarrangetype': '缸体形式',
            'engine.cylindernum': '气缸数',
            'engine.intakeform': '进气形式',
            'engine.fuelmethod': '供油方式',
            'engine.fuelgrade': '燃油标号',
            'engine.startstopsystem': '发动机启停',
            'engine.environmentalstandards': '环保标准',
            # 变速箱
            'gearbox.gearbox': '变速箱类型',
            'gearbox.levelnumber': '挡位个数',
            # 底盘制动
            'chassisbrake.drivemode': '驱动方式',
            'chassisbrake.frontsuspensiontype': '前悬架类型',
            'chassisbrake.rearsuspensiontype': '后悬架类型',
            'chassisbrake.adjustablesuspension': '可调悬架',
            'chassisbrake.frontbraketype': '前轮制动器类型',
            'chassisbrake.rearbraketype': '后轮制动器类型',
            'chassisbrake.parkingbraketype': '驻车制动类型',
            'chassisbrake.bodystructure': '车体结构',
            'chassisbrake.centerdifferentiallock': '限滑差速器/差速锁',
            # 安全配置
            'safe.abs': '防抱死制动(ABS)',
            'safe.ebd': '制动力分配(EBD/CBC等)',
            'safe.brakeassist': '制动辅助(BA/EBA/BAS等)',
            'safe.tractioncontrol': '牵引力控制(ARS/TCS/TRC等)',
            'safe.esp': '车身稳定控制(ESP/DSC/VSC等)',
            'safe.airbagdrivingposition': '主驾驶安全气囊',
            'safe.airbagfrontpassenger': '副驾驶安全气囊',
            'safe.airbagfrontside': '前侧气囊',
            'safe.airbagrearside': '后侧气囊',
            'safe.aircurtainside': '侧安全气帘',
            'safe.airbagknee': '膝部气囊',
            'safe.airbagseatbelt': '安全带气囊',
            'safe.airbagrearcenter': '后排中央气囊',
            'safe.tirepressuremonitoring': '胎压监测',
            'safe.zeropressurecontinued': '零胎压续行轮胎',
            'safe.isointerface': '后排儿童座椅接口(ISO FIX/LATCH)',
            'safe.centrallocking': '中控锁',
            'safe.intelligentkey': '智能钥匙',
            # 行车辅助
            'safe.cruisecontrol': '定速巡航',
            'safe.ldws': '车道保持',
            'safe.auxiliary': '并线辅助',
            'safe.activebraking': '碰撞报警/主动刹车',
            'safe.fatiguereminding': '疲劳提醒',
            'safe.automaticparkingintoplace': '自动泊车',
            'safe.pilotedparking': '遥控泊车',
            'safe.autopilotauxiliary': '自动驾驶辅助',
            'safe.automaticparking': '自动驻车',
            'safe.hillstartassist': '上坡辅助',
            'safe.hilldescent': '陡坡缓降',
            'safe.nightvisionsystem': '夜视系统',
            'safe.vgrs': '可变齿比转向',
            'safe.frontparkingradar': '前倒车雷达',
            'safe.reversingradar': '后倒车雷达',
            'safe.reverseimage': '倒车影像',
            'safe.drivemode': '驾驶模式选择',
            # 门窗/后视镜
            'doormirror.skylightstype': '天窗类型',
            'doormirror.frontelectricwindow': '前电动车窗',
            'doormirror.rearelectricwindow': '后电动车窗',
            'doormirror.externalmirroradjustment': '外后视镜电动调节',
            'doormirror.rearviewmirrorantiglare': '内后视镜自动防眩目',
            'doormirror.flowmediummirror': '流媒体后视镜',
            'doormirror.externalmirrorantiglare': '外后视镜自动防眩目',
            'doormirror.privacyglass': '隐私玻璃',
            'doormirror.rearwindowsunshade': '后遮阳帘',
            'doormirror.rearsidesunshade': '后排侧遮阳帘',
            'doormirror.frontwiper': '前雨刷器',
            'doormirror.rearwiper': '后雨刷器',
            'doormirror.electricpulldoor': '电吸门',
            # 车轮
            'wheel.fronttiresize': '前轮胎规格',
            'wheel.reartiresize': '后轮胎规格',
            'wheel.sparetiretype': '备胎',
            # 灯光
            'light.headlighttype': '前大灯',
            'light.daytimerunninglight': '	LED日间行车灯',
            'light.headlightautomaticopen': '自动大灯',
            'light.frontfoglight': '前雾灯',
            'light.headlightfunction': '大灯功能',
            # 内部配置
            'internalconfig.material': '内饰材质',
            'internalconfig.interiorairlight': '车内氛围灯',
            'internalconfig.sunvisormirror': '遮阳板化妆镜',
            'internalconfig.steeringwheelmaterial': '方向盘材质',
            'internalconfig.steeringwheelmultifunction': '多功能方向盘',
            'internalconfig.steeringwheeladjustment': '方向盘调节',
            'internalconfig.steeringwheelheating': '方向盘加热',
            'internalconfig.steeringwheelexchange': '方向盘换挡',
            # 座椅
            'seat.seatmaterial': '座椅材质',
            'seat.sportseat': '运动风格座椅',
            'seat.driverseatelectricadjustment': '主座椅电动调节',
            'seat.auxiliaryseatelectricadjustmentmode': '副座椅电动调节',
            'seat.driverseatadjustmentmode': '主座椅调节方式',
            'seat.auxiliaryseatadjustmentmode': '副座椅调节方式',
            'seat.secondrowseatadjustmentectricmode': '第二排座椅电动调节',
            'seat.secondrowseatadjustmentmode': '第二排座椅调节方式',
            'seat.frontcenterarmrest': '前排中央扶手',
            'seat.rearseatcenterarmrest': '后座中央扶手',
            'seat.thirdrowseat': '第三排座椅',
            'seat.seatdownmode': '座椅放倒方式',
            'seat.rearcupholder': '后排杯架',
            # 信息娱乐
            'entcom.consolelcdscreen': '中控彩色液晶屏',
            'entcom.alllcdpanels': '全液晶仪表盘',
            'entcom.computerscreen': '行车电脑显示屏',
            'entcom.huddisplay': '中控彩色液晶屏',
            'entcom.gps': 'GPS导航',
            'entcom.locationservice': '智能互联定位',
            'entcom.voicecontrol': '语音控制',
            'entcom.internetos': '手机互联(Carplay&Android)',
            'entcom.wirelesscharging': '手机无线充电',
            'entcom.gesturecontrol': '手势控制系统',
            'entcom.cddvd': 'CD/DVD',
            'entcom.bluetooth': '蓝牙/WIFI连接',
            'entcom.externalinterface': '外接接口',
            'entcom.cartv': '车载电视',
            'entcom.audiobrand': '音响品牌',
            'entcom.speakernum': '扬声器数量',
            'entcom.rearlcdscreen': '后排液晶屏/娱乐系统',
            'entcom.supplyvoltage': '车载220V电源',
            # 空调/冰箱
            'aircondrefrigerator.frontairconditioning': '前排空调',
            'aircondrefrigerator.rearairconditioning': '后排空调',
            'aircondrefrigerator.airconditioning': '香氛系统',
            'aircondrefrigerator.airpurifyingdevice': '空气净化',
            'aircondrefrigerator.carrefrigerator': '车载冰箱',
        }
        return params_dict

    @staticmethod
    def get_value(v):
        circle_unicode = u'\u25cf'
        line_unicode = u'-'
        if type(v) is list:
            v = ','.join(v)
        if type(v) is str:
            v = v.decode('utf-8')

        if (v == circle_unicode):
            return 1
        elif (v == line_unicode):
            return ''
        else:
            return v
