# API 说明文档

## 角色与认证信息
- **角色ID**: 2123487985
- **访问令牌(Token)**: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5IiwidHlwIjoiSldUIn0.eyJzY3AiOiJlc2ktd2FsbGV0LnJlYWRfY2hhcmFjdGVyX3dhbGxldC52MSIsImp0aSI6ImMzMjBiNzFjLWEyNzYtNDhhYy04ODQxLTgwNzEwNTg1ZDEyYyIsImtpZCI6IkpXVC1TaWduYXR1cmUtS2V5Iiwic3ViIjoiQ0hBUkFDVEVSOkVWRToyMTIzNDg3OTg1IiwiYXpwIjoiZGV2ZWxvcGVyc19ldmVvbmxpbmVfY29tIiwidGVuYW50IjoidHJhbnF1aWxpdHkiLCJ0aWVyIjoibGl2ZSIsInJlZ2lvbiI6IndvcmxkIiwiYXVkIjpbImRldmVsb3BlcnNfZXZlb25saW5lX2NvbSIsIkVWRSBPbmxpbmUiXSwibmFtZSI6IkFraXlhbWFNaTEiLCJvd25lciI6IjJtM1pNNE9mZHJaYUpieUVFR2xwdHpBaklpcz0iLCJleHAiOjE3NjYwMzkxODAsImlhdCI6MTc2NjAzNzk4MCwiaXNzIjoiaHR0cHM6Ly9sb2dpbi5ldmVvbmxpbmUuY29tIn0.IPD4rdh1-4ZIyF-q_QCIGi2WXeXE5F3NhjbNkXjajAjvNYkaU0vw-looZABBsx48IPsdgDyrxC2rEieqpWGBPDTwc2h9eDrlHonlh8s2TtJWNUU5TptLMBlVF9L3mr2ssXHHX6O9yyyXIP3iWURpyC-0LiNIuUHlC2xHE_24CfBegJMXnZtjsYeqnOWe6BOPVtUi07eDRYVct65Jupa0ftQUasNH9Lryv585UtX3Flixy-Mj-qBZAFUF3tDK2qxeOHpTlu-N4QAv_Z9PJJ3ouGawUZlJwhqVMaqEzdCwmirIUCORIrqx9Iu4Ai-WucpFUkXrJK3E_M1rsNHSnny9eQ

本文件用于记录项目中将要使用的所有API信息，包括API名称、端点URL、请求方法、参数说明、返回值等。

## 通用请求头信息
- **X-Compatibility-Date** (必填): 当前所有API使用的兼容日期，统一值为: `2026-06-09`
  - 注意：当EVE Online API更新时，可能需要修改此日期以保持兼容性

## 1. EVE Online API

### 1.1 获取市场物品组列表API
- **API名称**: Get item groups (获取市场物品组列表)
- **端点URL**: https://esi.evetech.net/markets/groups
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中所有市场物品组的ID列表。这些物品组构成了游戏内市场的分类体系，用于组织和分类各种可交易物品。
- **认证方式**: 无需认证
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    2, 4, 5, 6, 7, 8, 9, 10, 11, 14, 19, 20, 22, 23, 24, 27, 52, 54, 61, 64, 65, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 99, 100, 101, 102, 103, 105, 106, 107, 108, 109, 112, 113, 114, 115, 116, 117, 118, 120, 126, 128, 131, 132, 133, 134, 135, 139, 140, 141, 143, 150, 157, 158, 159, 204, 205, 206, 207, 208, 209, 210, 211, 214, 252, 261, 264, 272, 273, 274, 275, 276, 277, 278, 279, 280, 281, 282, 283, 284, 285, 286, 287, 288, 289, 290, 291, 292, 293, 295, 296, 297, 298, 299, 300, 301, 302, 303, 305, 306, 307, 308, 309, 312, 313, 314, 315, 316, 318, 320, 325, 331, 332, 335, 338, 339, 340, 341, 343, 357, 358, 359, 364, 365, 366, 367, 368, 369, 370, 372, 373, 374, 375, 376, 377, 378, 379, 380, 381, 382, 383, 387, 390, 391, 393, 394, 395, 396, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419, 420, 421, 422, 423, 424, 425, 427, 428, 429, 430, 432, 433, 434, 435, 436, 437, 438, 439, 440, 441, 442, 443, 444, 445, 446, 448, 449, 450, 451, 452, 453, 454, 455, 456, 457, 458, 459, 461, 462, 463, 464, 465, 466, 467, 468, 469, 470, 471, 472, 473, 475, 477, 478, 479, 480, 481, 482, 483, 484, 485, 488, 490, 491, 492, 494, 496, 497, 499, 500, 501, 502, 503, 504, 505, 506, 512, 514, 515, 516, 517, 518, 519, 521, 522, 523, 525, 526, 527, 528, 529, 530, 531, 532, 533, 535, 537, 538, 540, 541, 542, 550, 551, 552, 553, 554, 555, 556, 557, 558, 559, 560, 561, 562, 563, 564, 565, 566, 567, 568, 569, 570, 572, 573, 574, 575, 576, 577, 578, 579, 580, 581, 582, 583, 584, 585, 586, 588, 589, 590, 591, 592, 593, 594, 595, 596, 597, 598, 599, 600, 601, 602, 603, 604, 605, 606, 608, 609, 610, 611, 612, 613, 614, 615, 616, 617, 618, 619, 620, 621, 622, 629, 630, 631, 632, 633, 634, 635, 636, 637, 638, 639, 640, 641, 642, 643, 644, 645, 646, 647, 648, 655, 656, 657, 658, 659, 660, 661, 662, 663, 664, 665, 666, 667, 668, 669, 670, 671, 672, 673, 675, 676, 677, 678, 679, 680, 681, 683, 685, 686, 687, 688, 689, 690, 691, 692, 693, 694, 695, 696, 697, 698, 699, 700, 701, 702, 703, 704, 705, 706, 707, 708, 711, 712, 713, 714, 715, 716, 717, 718, 719, 720, 721, 722, 723, 724, 725, 726, 727, 728, 729, 730, 731, 732, 733, 734, 735, 736, 737, 738, 739, 740, 741, 742, 743, 744, 745, 746, 747, 748, 749, 750, 751, 752, 753, 754, 757, 761, 762, 763, 764, 765, 766, 767, 768, 769, 770, 771, 772, 773, 774, 775, 776, 777, 778, 779, 781, 782, 783, 784, 785, 786, 787, 788, 789, 790, 791, 792, 793, 794, 796, 798, 799, 800, 801, 802, 803, 812, 813, 814, 815, 816, 817, 818, 819, 820, 821, 822, 823, 824, 825, 826, 827, 828, 829, 830, 831, 832, 833, 834, 835, 836, 837, 838, 839, 840, 841, 842, 843, 845, 846, 847, 848, 849, 850, 851, 852, 853, 854, 855, 856, 857, 858, 859, 860, 861, 862, 863, 864, 865, 866, 867, 868, 869, 870, 871, 872, 874, 878, 879, 880, 881, 882, 883, 884, 885, 886, 887, 888, 889, 890, 891, 892, 893, 894, 895, 896, 897, 898, 899, 900, 901, 902, 903, 904, 905, 910, 911, 912, 913, 914, 917, 918, 919, 920, 921, 922, 923, 924, 925, 926, 927, 928, 929, 930, 931, 932, 933, 935, 937, 938, 939, 940, 943, 944, 945, 946, 948, 949, 950, 951, 952, 953, 954, 955, 956, 957, 958, 960, 961, 962, 963, 964, 965, 967, 968, 971, 972, 973, 974, 975, 977, 979, 983, 986, 987, 988, 989, 990, 991, 992, 993, 994, 995, 996, 997, 998, 999, 1000, 1001, 1002, 1003, 1004, 1006, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014, 1015, 1016, 1018, 1019, 1021, 1022, 1027, 1028, 1029, 1030, 1031, 1032, 1033, 1034, 1035, 1037, 1038, 1039, 1040, 1041, 1045, 1046, 1047, 1048, 1049, 1050, 1051, 1052, 1053, 1054, 1055, 1056, 1057, 1058, 1059, 1060, 1061, 1062, 1063, 1065, 1066, 1067, 1068, 1069, 1070, 1071, 1072, 1073, 1074, 1075, 1076, 1077, 1078, 1079, 1080, 1081, 1082, 1083, 1084, 1085, 1086, 1087, 1088, 1089, 1090, 1091, 1092, 1093, 1094, 1097, 1103, 1105, 1109, 1110, 1111, 1112, 1122, 1123, 1124, 1125, 1126, 1127, 1128, 1129, 1130, 1131, 1132, 1133, 1134, 1135, 1136, 1137, 1138, 1139, 1140, 1141, 1142, 1147, 1191, 1192, 1193, 1194, 1195, 1196, 1197, 1198, 1199, 1200, 1201, 1202, 1203, 1204, 1206, 1207, 1208, 1210, 1211, 1212, 1213, 1214, 1215, 1219, 1220, 1221, 1222, 1223, 1224, 1225, 1226, 1227, 1228, 1229, 1230, 1231, 1232, 1233, 1234, 1235, 1236, 1237, 1238, 1239, 1240, 1241, 1242, 1243, 1244, 1245, 1249, 1250, 1251, 1252, 1253, 1254, 1255, 1256, 1257, 1258, 1259, 1260, 1261, 1262, 1263, 1264, 1265, 1266, 1267, 1268, 1269, 1272, 1273, 1274, 1275, 1276, 1282, 1283, 1284, 1285, 1286, 1287, 1310, 1313, 1316, 1317, 1320, 1322, 1323, 1332, 1333, 1334, 1335, 1336, 1337, 1338, 1339, 1340, 1341, 1342, 1343, 1344, 1345, 1346, 1347, 1348, 1349, 1350, 1351, 1352, 1353, 1354, 1355, 1356, 1358, 1359, 1361, 1362, 1364, 1365, 1366, 1367, 1368, 1369, 1370, 1371, 1372, 1373, 1374, 1375, 1376, 1377, 1378, 1379, 1380, 1381, 1382, 1384, 1385, 1389, 1390, 1392, 1396, 1397, 1398, 1399, 1400, 1401, 1402, 1403, 1404, 1405, 1406, 1407, 1408, 1410, 1416, 1426, 1427, 1469, 1470, 1471, 1472, 1473, 1474, 1475, 1476, 1477, 1478, 1479, 1480, 1481, 1482, 1483, 1484, 1485, 1486, 1489, 1490, 1491, 1492, 1493, 1494, 1495, 1496, 1497, 1498, 1499, 1500, 1501, 1502, 1504, 1505, 1506, 1507, 1508, 1509, 1512, 1513, 1514, 1515, 1516, 1517, 1518, 1520, 1521, 1522, 1525, 1526, 1527, 1528, 1529, 1530, 1531, 1532, 1533, 1534, 1535, 1536, 1537, 1538, 1539, 1540, 1541, 1542, 1543, 1544, 1545, 1546, 1547, 1548, 1549, 1550, 1551, 1552, 1553, 1554, 1555, 1556, 1557, 1558, 1559, 1560, 1561, 1562, 1563, 1564, 1565, 1566, 1567, 1568, 1570, 1571, 1572, 1574, 1575, 1576, 1577, 1578, 1579, 1580, 1581, 1582, 1583, 1584, 1585, 1586, 1587, 1588, 1589, 1590, 1591, 1592, 1593, 1594, 1595, 1598, 1599, 1600, 1601, 1602, 1603, 1610, 1612, 1614, 1616, 1617, 1618, 1619, 1620, 1621, 1623, 1624, 1625, 1626, 1627, 1631, 1633, 1639, 1640, 1641, 1642, 1643, 1646, 1650, 1651, 1652, 1653, 1657, 1658, 1659, 1660, 1661, 1662, 1663, 1664, 1665, 1666, 1667, 1668, 1669, 1670, 1672, 1673, 1674, 1675, 1676, 1678, 1679, 1680, 1681, 1682, 1683, 1684, 1685, 1686, 1687, 1688, 1689, 1690, 1691, 1692, 1693, 1694, 1695, 1696, 1697, 1698, 1699, 1700, 1701, 1702, 1703, 1704, 1707, 1708, 1709, 1710, 1711, 1712
  ]
  ```
- **返回值说明**: 整数数组，包含EVE Online游戏中所有市场物品组的唯一标识符(ID)。这些ID是访问每个物品组详细信息的关键。
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - 需要提供`X-Compatibility-Date`请求头，当前允许值为`2026-06-09`
  - 返回的物品组ID可用于调用"根据物品组ID获取物品组信息API"获取具体的物品组详情
  - 物品组采用层级结构，通过父组ID组织成树状分类体系

### 1.2 根据物品组ID获取物品组信息API
- **API名称**: Get item group information（获取市场物品组详情）
- **端点URL**: https://esi.evetech.net/markets/groups/{market_group_id}
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定市场物品组的详细信息，包括物品组名称、描述、父组ID以及该物品组包含的所有物品类型ID列表。这是构建市场分类体系和获取物品组完整信息的关键API。
- **认证方式**: 无需认证
- **路径参数**:
  - `market_group_id` (必填): EVE物品组ID
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  {
    "description": "物品组描述",
    "market_group_id": 123,
    "name": "物品组名称",
    "parent_group_id": 456,
    "types": [
      12345, 67890
    ]
  }
  ```
- **返回值说明**:
  - `description`: 物品组的详细描述，说明该物品组包含的内容
  - `market_group_id`: 物品组的唯一标识符(ID)
  - `name`: 物品组的名称
  - `parent_group_id`: 父物品组的ID，用于构建物品组的层级结构（根物品组的parent_group_id为null）
  - `types`: 该物品组包含的所有物品类型ID的数组
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - 需要提供`X-Compatibility-Date`请求头，当前允许值为`2026-06-09`
  - `market_group_id`参数必须是有效的物品组ID，可通过"获取市场物品组列表API"获取
  - 当物品组为根物品组时，`parent_group_id`字段将返回null
  - `types`数组包含该物品组下所有可交易物品的类型ID，可用于进一步获取物品的详细信息

### 1.3 获取物品类型ID列表API
- **API名称**: Get types (获取物品类型ID列表)
- **端点URL**: https://esi.evetech.net/universe/types
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中所有物品类型的ID列表。这些物品类型ID是访问每个物品详细信息的关键。
- **认证方式**: 无需认证
- **查询参数**:
  - `page` (可选): 结果的页码，用于分页获取所有物品类型ID，默认值为1，最小值为1，
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30
  ]
  ```
- **返回值说明**: 整数数组，包含EVE Online游戏中所有物品类型的唯一标识符(ID)。这些ID是访问每个物品详细信息的关键。
- **错误处理**:
  - 当请求的页码超出有效范围时，API将返回404 Not Found错误，错误响应示例：
    ```json
    {
      "error": "Requested page does not exist!"
    }
    ```
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - 需要提供`X-Compatibility-Date`请求头，当前允许值为`2026-06-09`
  - 使用`page`参数可以分页获取所有物品类型ID，每页返回一定数量的结果
  - 请确保请求的页码在有效范围内，避免404错误
  - 返回的物品类型ID可用于进一步获取物品的详细信息

### 1.4 获取物品信息API
- **API名称**: Get type information (获取物品信息)
- **端点URL**: https://esi.evetech.net/universe/types/{type_id}
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定物品类型的详细信息，包括物品名称、描述、属性、效果等。
- **认证方式**: 无需认证
- **路径参数**:
  - `type_id` (必填): 物品类型ID，用于指定要获取的物品信息
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  {
    "capacity": 0,
    "description": "string",
    "dogma_attributes": [
      {
        "attribute_id": 0,
        "value": 0
      }
    ],
    "dogma_effects": [
      {
        "effect_id": 0,
        "is_default": true
      }
    ],
    "graphic_id": 0,
    "group_id": 0,
    "icon_id": 0,
    "market_group_id": 0,
    "mass": 0,
    "name": "string",
    "packaged_volume": 0,
    "portion_size": 0,
    "published": true,
    "radius": 0,
    "type_id": 0,
    "volume": 0
  }
  ```
- **返回值说明**:
  - `capacity`: 物品的容量
  - `description`: 物品的详细描述
  - `dogma_attributes`: 物品的Dogma属性数组
    - `attribute_id`: 属性ID
    - `value`: 属性值
  - `dogma_effects`: 物品的Dogma效果数组
    - `effect_id`: 效果ID
    - `is_default`: 是否为默认效果
  - `graphic_id`: 物品的图形ID
  - `group_id`: 物品所属的物品组ID
  - `icon_id`: 物品的图标ID
  - `market_group_id`: 物品所属的市场组ID（仅适用于可交易物品）
  - `mass`: 物品的质量
  - `name`: 物品的名称
  - `packaged_volume`: 物品打包后的体积
  - `portion_size`: 物品的部分大小
  - `published`: 物品是否已发布
  - `radius`: 物品的半径
  - `type_id`: 物品的类型ID
  - `volume`: 物品的体积
- **错误处理**:
  - 当请求的`type_id`无效时，API将返回404 Not Found错误，错误响应示例：
    ```json
    {
      "error": "failed to coerce value '{type_id}' into type integer (format: int32), 'type_id' is required"
    }
    ```
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - 需要提供`X-Compatibility-Date`请求头，当前允许值为`2026-06-09`
  - `type_id`参数必须是有效的物品类型ID，可通过"获取物品类型ID列表API"获取
  - 仅可交易物品会返回`market_group_id`字段
  - 返回的物品信息可用于构建物品详细页面和市场分析功能

### 1.5 获取区域市场订单API
- **API名称**: List orders in a region (获取区域市场订单列表)
- **端点URL**: https://esi.evetech.net/markets/{region_id}/orders
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定区域的市场订单列表，包括买单和卖单信息。
- **缓存信息**: 此路由缓存5分钟
- **认证方式**: 无需认证
- **路径参数**:
  - `region_id` (必填): 区域ID，返回该区域的订单
- **查询参数**:
  - `order_type` (必填): 过滤买单/卖单，默认返回所有订单
    - 允许值: buy, sell, all
    - 默认值: all
  - `page` (可选): 返回结果的页码，最小值为1
  - `type_id` (可选): 仅返回该物品类型的订单
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    {
      "duration": 0,
      "is_buy_order": true,
      "issued": "2019-08-24T14:15:22Z",
      "location_id": 0,
      "min_volume": 0,
      "order_id": 0,
      "price": 0,
      "range": "station",
      "system_id": 0,
      "type_id": 0,
      "volume_remain": 0,
      "volume_total": 0
    }
  ]
  ```
- **返回值说明**:
  - `duration`: 订单持续时间
  - `is_buy_order`: 是否为买单
  - `issued`: 订单发布时间
  - `location_id`: 订单所在位置ID
  - `min_volume`: 最小交易量
  - `order_id`: 订单ID
  - `price`: 订单价格
  - `range`: 订单范围
    - 允许值: station, region, solarsystem, 1, 2, 3, 4, 5, 10, 20, 30, 40
  - `system_id`: 订单所在太阳系ID
  - `type_id`: 物品类型ID
  - `volume_remain`: 剩余数量
  - `volume_total`: 总数量
- **注意事项**:
  - 此路由缓存5分钟，建议合理设置缓存策略
  - 当未查询type_id时，总是返回买单和卖单
  - `region_id`参数必须是有效的区域ID
  - 使用`page`参数可以分页获取所有订单
  - `range`字段表示订单的有效范围，如station表示仅在该空间站有效，region表示整个区域有效

### 1.6 获取星域ID列表API
- **API名称**: Get regions (获取星域ID列表)
- **端点URL**: https://esi.evetech.net/universe/regions
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中所有星域的ID列表。这些星域ID是访问每个星域详细信息的关键。
- **过期时间**: 此路由每天在UTC时间11:05过期
- **认证方式**: 无需认证
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    10000001, 10000002, 10000003, 10000004, 10000005, 10000006, 10000007, 10000008, 10000009, 10000010
  ]
  ```
- **返回值说明**: 整数数组，包含EVE Online游戏中所有星域的唯一标识符(ID)。这些ID是访问每个星域详细信息的关键。
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - 返回的星域ID可用于进一步获取星域的详细信息
  - 使用`Accept-Language`头可以获取本地化的响应（如果支持）

### 1.7 获取星域信息API
- **API名称**: Get region information (获取星域信息)
- **端点URL**: https://esi.evetech.net/universe/regions/{region_id}
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定星域的详细信息。
- **过期时间**: 此路由每天在UTC时间11:05过期
- **认证方式**: 无需认证
- **路径参数**:
  - `region_id` (必填): 星域ID，用于指定要获取的星域
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  {
    "constellations": [
      0
    ],
    "description": "string",
    "name": "string",
    "region_id": 0
  }
  ```
- **返回值说明**:
  - `constellations`: 该星域包含的星座ID数组
  - `description`: 星域的详细描述
  - `name`: 星域的名称
  - `region_id`: 星域的ID
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - `region_id`参数必须是有效的星域ID，可通过"获取星域ID列表API"获取
  - 使用`Accept-Language`头可以获取本地化的响应（如果支持）
  - 响应头中的`Content-Language`字段会标明实际返回内容的语言

### 1.8 获取某星域历史订单API
- **API名称**: List historical market statistics in a region (获取某星域历史订单)
- **端点URL**: https://esi.evetech.net/markets/{region_id}/history
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定类型在某星域的历史市场统计数据。
- **过期时间**: 此路由每天在UTC时间11:05过期
- **认证方式**: 无需认证
- **路径参数**:
  - `region_id` (必填): 星域ID，返回该星域的统计数据
- **查询参数**:
  - `type_id` (必填): 物品类型ID，返回该类型的统计数据
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    {
      "average": 0,
      "date": "2019-08-24",
      "highest": 0,
      "lowest": 0,
      "order_count": 0,
      "volume": 0
    }
  ]
  ```
- **返回值说明**:
  - `average`: 平均价格
  - `date`: 历史统计记录的日期
  - `highest`: 最高价格
  - `lowest`: 最低价格
  - `order_count`: 当天发生的订单总数
  - `volume`: 当天的总交易量
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - `region_id`和`type_id`参数都是必填的
  - 使用`Accept-Language`头可以获取本地化的响应（如果支持）
  - 响应头中的`Content-Language`字段会标明实际返回内容的语言

### 1.9 获取星座ID列表API
- **API名称**: Get constellations (获取星座ID列表)
- **端点URL**: https://esi.evetech.net/universe/constellations
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中所有星座的ID列表。这些星座ID是访问每个星座详细信息的关键。
- **过期时间**: 此路由每天在UTC时间11:05过期
- **认证方式**: 无需认证
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    20000001, 20000002, 20000003, 20000004, 20000005
  ]
  ```
- **返回值说明**: 整数数组，包含EVE Online游戏中所有星座的唯一标识符(ID)。这些ID是访问每个星座详细信息的关键。
- **响应头**:
  - `Cache-Control`: 缓存控制指令，控制响应的缓存方式、缓存者和缓存时间
  - `ETag`: 响应体的ETag值，用于与If-None-Match配合进行缓存验证
  - `Last-Modified`: 响应的最后修改日期，用于与If-Modified-Since配合进行缓存验证
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - 使用`Accept-Language`头可以获取本地化的响应（如果支持）
  - 返回的星座ID可用于进一步获取星座的详细信息

### 1.10 获取星座信息API
- **API名称**: Get constellation information (获取星座信息)
- **端点URL**: https://esi.evetech.net/universe/constellations/{constellation_id}
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定星座的详细信息，包括星座名称、位置、所属星域以及包含的太阳系列表。
- **过期时间**: 此路由每天在UTC时间11:05过期
- **认证方式**: 无需认证
- **路径参数**:
  - `constellation_id` (必填): 星座ID，用于指定要获取的星座
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  {
    "constellation_id": 20000001,
    "name": "星座名称",
    "position": {
      "x": 0,
      "y": 0,
      "z": 0
    },
    "region_id": 10000001,
    "systems": [
      30000001, 30000002, 30000003
    ]
  }
  ```
- **返回值说明**:
  - `constellation_id`: 星座的唯一标识符(ID)
  - `name`: 星座的名称
  - `position`: 星座在游戏宇宙中的三维坐标
    - `x`: X坐标
    - `y`: Y坐标
    - `z`: Z坐标
  - `region_id`: 星座所属的星域ID
  - `systems`: 星座包含的太阳系ID数组
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息

### 1.11 获取角色钱包日志API
- **API名称**: Get character wallet journal (获取角色钱包日志)
- **端点URL**: https://esi.evetech.net/characters/{character_id}/wallet/journal
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定角色最近30天的钱包日志记录。
- **缓存信息**: 此路由缓存1小时
- **认证方式**: 需要OAuth 2.0认证，使用Authorization Code授权流程
- **所需权限**: esi-wallet.read_character_wallet.v1
- **路径参数**:
  - `character_id` (必填): 角色ID，用于指定要获取钱包日志的角色
- **查询参数**:
  - `page` (可选): 结果的页码，最小值为1
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Authorization` (必填): Bearer {access_token}，包含访问令牌
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    {
      "amount": 0,
      "balance": 0,
      "context_id": 0,
      "context_id_type": "structure_id",
      "date": "2019-08-24T14:15:22Z",
      "description": "string",
      "first_party_id": 0,
      "id": 0,
      "reason": "string",
      "ref_type": "acceleration_gate_fee",
      "second_party_id": 0,
      "tax": 0,
      "tax_receiver_id": 0
    }
  ]
  ```
- **返回值说明**:
  - `amount`: 交易涉及的ISK数量，正数表示存入，负数表示取出
  - `balance`: 交易发生后的钱包余额
  - `context_id`: 交易的额外上下文ID，根据ref_type的不同含义不同
  - `context_id_type`: 上下文ID的类型，如structure_id、station_id等
  - `date`: 交易发生的日期和时间
  - `description`: 交易的原因描述
  - `first_party_id`: 交易的第一方ID
  - `id`: 交易的唯一标识符
  - `reason`: 用户为交易提供的原因（仅适用于某些ref_type）
  - `ref_type`: 交易类型，如acceleration_gate_fee、bounty等
  - `second_party_id`: 交易的第二方ID
  - `tax`: 支付的税费金额（仅适用于与税收相关的交易）
  - `tax_receiver_id`: 接收税费的公司ID（仅适用于与税收相关的交易）
- **速率限制**: 此API属于char-wallet速率限制组，每15分钟限制150个令牌
- **注意事项**:
  - 需要有效的OAuth 2.0访问令牌和相应的权限
  - 仅返回最近30天的钱包日志记录
  - 使用`page`参数可以分页获取所有日志记录
  - `context_id`和`context_id_type`字段的含义因`ref_type`而异

### 1.12 获取角色钱包余额API
- **API名称**: Get a character's wallet balance (获取角色钱包余额)
- **端点URL**: https://esi.evetech.net/characters/{character_id}/wallet
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定角色的钱包余额。
- **缓存信息**: 此路由缓存2分钟
- **认证方式**: 需要OAuth 2.0认证，使用Authorization Code授权流程
- **所需权限**: esi-wallet.read_character_wallet.v1
- **路径参数**:
  - `character_id` (必填): 角色ID，用于指定要获取钱包余额的角色
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Authorization` (必填): Bearer {access_token}，包含访问令牌
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  123456789.0
  ```
- **返回值说明**: 返回一个浮点数，表示角色的当前钱包余额（单位：ISK）
- **速率限制**: 此API属于char-wallet速率限制组，每15分钟限制150个令牌
- **注意事项**:
  - 需要有效的OAuth 2.0访问令牌和相应的权限
  - 返回的是角色的总钱包余额，不区分不同的钱包类型（如主钱包、企业钱包等）
  - 缓存时间较短（2分钟），适合频繁查询

### Python示例代码

#### 获取角色钱包日志
```python
import http.client

conn = http.client.HTTPSConnection("esi.evetech.net")

headers = {
    'Accept-Language': "",
    'If-None-Match': "",
    'X-Compatibility-Date': "2026-06-09",
    'X-Tenant': "",
    'Accept': "application/json",
    'Authorization': "Bearer YOUR_ACCESS_TOKEN"
}

conn.request("GET", "/characters/2123487985/wallet/journal", headers=headers)

res = conn.getresponse()
data = res.read()

print(data.decode("utf-8"))
```

#### 获取角色钱包余额
```python
import http.client

conn = http.client.HTTPSConnection("esi.evetech.net")

headers = {
    'Accept-Language': "",
    'If-None-Match': "",
    'X-Compatibility-Date': "2026-06-09",
    'X-Tenant': "",
    'Accept': "application/json",
    'Authorization': "Bearer YOUR_ACCESS_TOKEN"
}

conn.request("GET", "/characters/2123487985/wallet", headers=headers)

res = conn.getresponse()
data = res.read()

print(data.decode("utf-8"))
```


### 1.11 获取恒星系ID列表API
- **API名称**: Get solar systems (获取恒星系ID列表)
- **端点URL**: https://esi.evetech.net/universe/systems
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中所有恒星系的ID列表。这些恒星系ID是访问每个恒星系详细信息的关键。
- **过期时间**: 此路由每天在UTC时间11:05过期
- **认证方式**: 无需认证
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    30000001, 30000002, 30000003, 30000004, 30000005
  ]
  ```
- **返回值说明**: 整数数组，包含EVE Online游戏中所有恒星系的唯一标识符(ID)。这些ID是访问每个恒星系详细信息的关键。
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - 使用`Accept-Language`头可以获取本地化的响应（如果支持）
  - 返回的恒星系ID可用于进一步获取恒星系的详细信息

### 1.12 获取恒星系信息API
- **API名称**: Get solar system information (获取恒星系信息)
- **端点URL**: https://esi.evetech.net/universe/systems/{system_id}
- **请求方法**: GET
- **功能描述**: 获取EVE Online游戏中指定恒星系的详细信息，包括恒星系名称、位置、所属星座、行星、小行星带、卫星、安全状态等信息。
- **过期时间**: 此路由每天在UTC时间11:05过期
- **认证方式**: 无需认证
- **路径参数**:
  - `system_id` (必填): 恒星系ID，用于指定要获取的恒星系
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  {
    "constellation_id": 20000001,
    "name": "恒星系名称",
    "planets": [
      {
        "asteroid_belts": [
          40000001, 40000002
        ],
        "moons": [
          40000003, 40000004
        ],
        "planet_id": 40000005
      }
    ],
    "position": {
      "x": 0,
      "y": 0,
      "z": 0
    },
    "security_class": "K",
    "security_status": 0.9,
    "star_id": 50000001,
    "stargates": [
      50000002, 50000003
    ],
    "stations": [
      60000001, 60000002
    ],
    "system_id": 30000001
  }
  ```
- **返回值说明**:
  - `constellation_id`: 恒星系所属的星座ID
  - `name`: 恒星系名称
  - `planets`: 恒星系中的行星列表
    - `asteroid_belts`: 小行星带ID列表
    - `moons`: 卫星ID列表
    - `planet_id`: 行星ID
  - `position`: 恒星系在游戏宇宙中的三维坐标
    - `x`: X坐标
    - `y`: Y坐标
    - `z`: Z坐标
  - `security_class`: 安全等级类别（如K、L等）
  - `security_status`: 安全状态值（0.0-1.0）
  - `star_id`: 恒星ID
  - `stargates`: 星门ID列表
  - `stations`: 空间站ID列表
  - `system_id`: 恒星系ID
- **注意事项**:
  - 此路由每天在UTC时间11:05过期，建议在此时间后刷新数据以获取最新信息
  - `system_id`参数必须是有效的恒星系ID，可通过"获取恒星系ID列表API"获取
  - 使用`Accept-Language`头可以获取本地化的响应（如果支持）
  - 响应头中的`Content-Language`字段会标明实际返回内容的语言

### 1.15 获取区域活跃订单物品类型ID列表API
- **API名称**: Get market active order types (获取区域活跃订单物品类型ID列表)
- **端点URL**: https://esi.evetech.net/markets/{region_id}/types
- **请求方法**: GET
- **功能描述**: 获取指定区域内具有活跃订单的物品类型ID列表，用于高效的市场索引。这是获取特定区域市场活跃物品的关键API。
- **认证方式**: 无需认证
- **路径参数**:
  - `region_id` (必填): 区域ID，用于指定要查询的市场区域
- **查询参数**:
  - `page` (可选): 结果的页码，用于分页获取所有物品类型ID，默认值为1，最小值为1
- **请求头要求**:
  - `X-Compatibility-Date` (必填): 请求的兼容日期，当前允许值: 2026-06-09
  - `Accept-Language` (可选): 响应语言，默认: en，支持: en, de, fr, ja, ru, zh, ko, es
  - `If-None-Match` (可选): 上一次请求的ETag，用于缓存验证
  - `X-Tenant` (可选): 租户ID，默认: tranquility（宁静服务器）
- **返回值示例**:
  ```json
  [
    0
  ]
  ```
- **返回值说明**: 整数数组，包含指定区域内所有具有活跃订单的物品类型ID。
- **响应头说明**:
  - `Cache-Control`: 缓存控制指令，控制响应的缓存方式、缓存者和缓存时长
  - `ETag`: 响应体的ETag值，与If-None-Match一起使用以检查资源是否已更改
  - `Last-Modified`: 响应的最后修改日期，与If-Modified-Since一起使用以检查资源是否已更改
  - `X-Pages`: 结果集中的总页数
- **注意事项**:
  - 此路由缓存10分钟，建议在缓存时间内复用响应数据
  - 需要提供有效的区域ID作为路径参数
  - 使用Accept-Language头可以获取本地化的响应（如果支持）

## 3. API使用注意事项
1. **错误处理**: 实现适当的错误处理机制，处理API返回的错误码
2. **缓存策略**: 对频繁请求的数据实现缓存，减少API调用次数
3. **版本控制**: 使用指定的API版本，避免版本变更导致的兼容性问题

## 4. 速率限制与避免方式

### 4.1 ESI API速率限制机制

#### 4.1.1 新版浮动窗口速率限制
- **基于令牌桶机制**：不同状态码消耗不同令牌
  - 2xx响应：消耗2个令牌
  - 3xx响应：消耗1个令牌
  - 4xx响应：消耗5个令牌
  - 5xx响应：消耗0个令牌
- **动态调整**：根据服务器负载动态调整令牌生成速率
- **响应头信息**：通过以下响应头获取速率限制状态
  - `X-Ratelimit-Limit`：当前窗口的令牌总数
  - `X-Ratelimit-Remaining`：当前窗口剩余令牌数
  - `X-Ratelimit-Reset`：当前窗口重置时间（Unix时间戳）

#### 4.1.2 旧版错误速率限制
- **限制规则**：每分钟最多允许100个非2xx/3xx响应
- **处罚机制**：超出限制后，所有ESI路由将返回420错误（"Enhance Your Calm"）
- **影响范围**：即使启用了新版速率限制的路由也会受到影响

### 4.2 常见错误码及处理方式

#### 429 Too Many Requests
- **原因**：超出新版速率限制
- **处理方式**：
  - 实现指数退避重试机制
  - 等待`X-Ratelimit-Reset`时间后重试
  - 减少并发请求数

#### 420 Enhance Your Calm
- **原因**：超出旧版错误速率限制（每分钟>100个非2xx/3xx响应）
- **处理方式**：
  - 至少等待60秒后重试
  - 添加随机抖动（如60-70秒）避免同时重试
  - 检查并减少非2xx/3xx响应的产生

#### 404 Not Found
- **原因**：请求的资源不存在或页码超出范围
- **处理方式**：
  - 优化分页查询逻辑，避免查询不存在的页码
  - 检查请求参数的有效性

### 4.3 避免速率限制的最佳实践

#### 4.3.1 分页优化
- **终止条件优化**：将分页终止条件从"查询到404"改为"数据量小于每页最大数量1000"
- **减少无效请求**：避免请求超出实际数据范围的页码
- **示例代码逻辑**：
  ```python
  max_page_size = 1000
  while True:
      # 发起API请求
      if len(data) < max_page_size:
          # 已到达最后一页
          break
      page += 1
  ```

#### 4.3.2 并发控制
- **使用Semaphore限制并发数**：避免同时发起过多请求
- **示例代码**：
  ```python
  import asyncio
  semaphore = asyncio.Semaphore(50)  # 限制50个并发请求
  ```

#### 4.3.3 批量处理
- **分批处理大量数据**：将18,000+活跃物品类型ID按批次（每批500个）处理
- **降低内存占用**：减少单次处理的数据量
- **便于进度监控**：更容易跟踪处理进度和错误

#### 4.3.4 错误减少策略
- **只查询活跃订单**：通过`/markets/{region_id}/types`端点获取仅含活跃订单的物品类型ID
- **减少404响应**：优化分页逻辑，避免查询不存在的页码
- **缓存响应数据**：合理利用API缓存机制，减少重复请求

#### 4.3.5 事件循环优化（Windows环境）
- **使用SelectorEventLoop**：避免Windows默认ProactorEventLoop的事件循环关闭错误
- **示例代码**：
  ```python
  import asyncio
  if sys.platform == 'win32':
      asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
  ```
