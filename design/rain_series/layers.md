| Layer                 | Category          | 典型关键词（Keywords）                                                                                                                                                                  |
| --------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Rain**       | Intensity         | Drizzle、Light、Moderate、Heavy、Downpour                                                                                                                                            |
|                       | Distance（可选）      | Far、Mid、Near、Overhead                                                                                                                                                            |
|                       | Perspective（可选）   | Indoor、Outdoor、Covered、Open                                                                                                                                                      |
| **2. Impact**    | Vegetation        | Leaves、Pine Needles、Branches、Grass、Bushes、Fern、Moss、Bamboo、Reeds、Fallen Leaves、Tree Bark                                                                                         |
|                       | Wood              | Wood Roof、Cabin Roof、Deck、Fence、Bridge、Bench、Log、Wood Wall                                                                                                                       |
|                       | Metal             | Tin Roof、Metal Roof、Steel Plate、Metal Fence、Drain Cover、Metal Stairs                                                                                                             |
|                       | Glass             | Window、Glass Roof、Glass Door、Skylight、Window Sill                                                                                                                                |
|                       | Stone             | Rock、Pebble、Gravel、Stone Path、Cliff、Boulder                                                                                                                                      |
|                       | Ground            | Soil、Mud、Concrete、Asphalt、Brick、Sand、Wood Chips                                                                                                                                  |
|                       | Water             | Lake、River、Pond、Puddle、Stream、Wet Ground                                                                                                                                         |
|                       | Fabric            | Tent、Canvas、Umbrella、Tarp                                                                                                                                                        |
| **3. Environment**    | Air               | Forest Air、Mountain Air、Lake Air、Open Air、Wetland Air                                                                                                                            |
|                       | Wind              | Forest Wind、Canopy Wind、Mountain Wind、Valley Wind、Shore Wind                                                                                                                     |
|                       | Ambience          | Forest Ambience、Deep Forest Ambience、Lake Ambience、Mountain Ambience、River Ambience、Wetland Ambience、Marsh Ambience、Countryside Ambience、Garden Ambience、Cabin Exterior Ambience |
|                       | Room Tone         | Forest Room Tone、Outdoor Room Tone、Cabin Room Tone                                                                                                                               |
| **4. Water Movement** | Dripping          | Leaf Drip、Branch Drip、Roof Drip、Window Drip、Rock Drip                                                                                                                            |
|                       | Flow              | Runoff、Gutter、Drain Pipe、Water Channel、Overflow                                                                                                                                  |
|                       | Stream            | Creek、Brook、Stream、Small Waterfall                                                                                                                                               |
|                       | Standing Water    | Puddle、Standing Water、Ripples、Splash                                                                                                                                             |
| **5. Wildlife**       | Birds             | Robin、Sparrow、Blackbird、Crow、Woodpecker、Owl、Duck、Goose、Swan                                                                                                                      |

### 场景常见鸟类（叫声素材目录 `5_wildlife/birds/`）

| 场景 | 常见鸟类 | 说明 |
| ---- | -------- | ---- |
| **森林** | Robin（鸫）、Sparrow（雀）、Blackbird（乌鸫）、Crow（鸦）、Woodpecker（啄木鸟）、Owl（猫头鹰） | 林冠层与灌丛鸣禽为主，辅以鸦科、啄木鸟与夜行猫头鹰 |
| **湖边** | Duck（鸭）、Goose（鹅）、Swan（天鹅） | 水禽鸣叫、振翅、戏水声 |
| **小溪** | Duck、Sparrow、Robin | 近水灌丛雀类 + 溪边水禽，体量较轻 |

声源库目标：上述 9 个物种各 **Epidemic×10 + Envato×10**（`python3 scripts/sound_effect/fill_rain_sound.py --fill-birds-stores`）。

|                       | Amphibians        | Tree Frog、Bullfrog、Marsh Frog                                                                                                                                                    |
|                       | Insects           | Cricket、Katydid、Cicada、Bee、Dragonfly                                                                                                                                             |
|                       | Mammals（可选）       | Deer、Fox、Wolf、Horse、Cow、Sheep                                                                                                                                                    |
| **6. Human Presence** | Fire              | Fireplace、Wood Stove、Fire Crackle                                                                                                                                                |
|                       | Cabin / House     | Clock、Floor Creak、Chair Creak、Door Creak、Window Creak、Wood Expansion                                                                                                             |
|                       | Reading / Working | Book Pages、Writing、Keyboard、Mouse、Tea Cup、Coffee Cup                                                                                                                             |
|                       | Tent              | Tent Fabric、Canvas Flap、Sleeping Bag、Tent Zipper                                                                                                                                 |
|                       | Indoor            | Ceiling Fan、Air Conditioner、Curtain、Blanket Rustle                                                                                                                               |

---

## 我建议再做一个小调整（更符合 Rain ASMR）

如果你的**90% 视频都是雨声**，我建议把 **Rain Impact** 再按**重要性**排序，而不是按材质排序。

| 优先级   | Category           | 为什么                     |
| ----- | ------------------ | ----------------------- |
| ⭐⭐⭐⭐⭐ | Vegetation         | 森林雨、湖边雨最常用，也是最舒适的声音。    |
| ⭐⭐⭐⭐⭐ | Roof（Wood / Metal） | 木屋雨、铁皮屋雨是 YouTube 热门场景。 |
| ⭐⭐⭐⭐☆ | Glass              | 雨打窗户非常经典。               |
| ⭐⭐⭐⭐☆ | Water              | 雨打湖面、积水、溪流变化丰富。         |
| ⭐⭐⭐☆☆ | Ground             | 泥地、混凝土、石板路等。            |
| ⭐⭐☆☆☆ | Fabric             | 帐篷、雨伞等特定场景。             |
| ⭐⭐☆☆☆ | Stone              | 山谷、岩石场景才会大量使用。          |

这样你的素材收集可以遵循 **80/20 原则**：

* **先收集 Vegetation、Roof、Glass、Water** 四大类，就已经能覆盖大多数热门雨声场景（森林、木屋、湖边、窗边、帐篷）。
* **Stone、Ground、Fabric** 可以作为后续扩展，不需要一开始就投入大量时间。这样既符合实际制作需求，也能更快建立起一套高质量、可复用的 Rain 素材库。
