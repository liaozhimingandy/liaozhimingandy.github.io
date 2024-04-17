<template>
  <div style="height: 100vh">
    <el-auto-resizer>
      <template #default="{ height, width }">
        <el-table-v2
            :columns="fixColumns"
            :data="filter_data"
            :width="width"
            :height="height"
            fixed
            v-if="data.data"
        />
      </template>
    </el-auto-resizer>
  </div>
</template>

<style scoped>

</style>

<script setup lang="jsx">

import {onMounted, reactive, ref} from "vue";
import service from "@/services";
import {API_ENDPOINTS as api} from "@/services/api";
import {
  ElNotification,
  ElTableV2,
  ElAutoResizer,
  ElPopover,
  ElCheckboxGroup,
  ElCheckbox,
  ElIcon,
  ElButton,
  ElScrollbar
} from "element-plus";
import {Filter} from '@element-plus/icons-vue';
import {generalArrFilterHandler, generalFilterHandler} from "@/common/el-table-v2-utils";

const data = reactive({'data': null});
const filter_data = ref([]);
const columns = ref([
  {
    key: 'id',
    dataKey: "index",//需要渲染当前列的数据字段，如{id:9527,name:'Mike'}，则填id
    title: "序号",//显示在单元格表头的文本
    width: 80,//当前列的宽度，必须设置
    fixed: false,//是否固定列
  },
  {
    key: "desc",
    dataKey: "desc",//需要渲染当前列的数据字段，如{id:9527,name:'Mike'}，则填name
    title: "字典表名称",
    width: 300,
    filterable: true,
    filterMethod: generalArrFilterHandler
  },
  {
    key: "value",
    dataKey: "value",//需要渲染当前列的数据字段，如{id:9527,name:'Mike'}，则填name
    title: "值",
    width: 100,
  },
  {
    key: "comment",
    dataKey: "comment",//需要渲染当前列的数据字段，如{id:9527,name:'Mike'}，则填name
    title: "值含义",
    width: 300,
  },
  {
    key: "dict_name",
    dataKey: "dict_name",//需要渲染当前列的数据字段，如{id:9527,name:'Mike'}，则填name
    title: "参考标准",
    width: 100,
  }
])

const fixColumns = columns.value.map(item => {
  // 参考文档: https://blog.csdn.net/ymzhaobth/article/details/129493380
  return {
    key: item.dataKey,
    title: item.title,
    dataKey: item.dataKey,
    width: item.width ?? 200,
    headerCellRenderer: (props) => {
      if (!item.filterable) return props.column.title
      return <div class="tbv2-th-filter">
        <span class="th-cell">{props.column.title}</span>
        <ElPopover trigger="hover" {...{width: 200}}>
          {{
            default: () => (
                <div class="filter-wrapper">
                  <div class="filter-group">
                    <ElScrollbar height="400px">
                      <ElCheckboxGroup v-model={filterableCols[item.dataKey].selected}>
                        {
                          filterableCols[item.dataKey].list.map(f => <ElCheckbox key={f.value}
                                                                                 label={f.text}>{f.text}</ElCheckbox>)
                        }
                      </ElCheckboxGroup>
                    </ElScrollbar>
                  </div>
                  <div class="mt-3 text-center">
                    <ElButton onClick={onFilter} type="primary">
                      确认
                    </ElButton>
                    <ElButton onClick={()=>onReset(item.dataKey)} type="danger">
                      重置
                    </ElButton>
                  </div>
                </div>
            ),
            reference: () => (
                <ElIcon class="cursor-pointer">
                  <Filter/>
                </ElIcon>
            ),
          }}
        </ElPopover>
      </div>
    }
  }
})

/**
 * 筛选信息列表
 * props:
 * - {Array} list 可筛选值列表
 * - {Array} selected 已勾选列表
 * - {Function} [filterMethod] 筛选方法
 */
const filterableCols = reactive(
    columns.value
        .filter(c => c.filterable)
        .reduce((prev, curr) => {
          prev[curr.dataKey] = {
            selected: [],
            list: [],
            filterMethod: curr.filterMethod ?? generalFilterHandler
          }
          return prev
        }, {})
);

const onFilter = () => {
  // console.info(Object.entries(filterableCols))
  const allFilters = Object.entries(filterableCols).filter(configs => configs[1].selected?.length > 0)

  filter_data.value = data.data.filter(p => {
    return allFilters.every(([dataKey,configs]) => {
      return !configs.filterMethod || configs.filterMethod(p[dataKey], configs.selected)
    })
  })
};

// 重置筛选
const onReset = (el) => {
  filterableCols[el].selected = [];
  onFilter();
};

onMounted(() => {
      service.get(api.LIST_HIP_DICT)
          .then(response => {
            // data.data = response.data;
            const list = [];
            response.data.forEach((item) => {
              list.push({index: item[0], dict_name: item[4], value: item[2], comment: item[3], desc: item[1]});
            });
            data.data = list;
            filter_data.value = list;
            // 处理过滤列表
            for (let item in filterableCols) {
              let map = new Map()
              let list;
              // 去重、转对象
              list = response.data.map(el => ({text: el[1], value: el[4]}));
              list.filter(item => map.set(item['value'].toString(), item['text']) && !map.has(item['value'].toString()))
              filterableCols[item].list = [...map].map(item => ({'value': item[0], 'text': item[1]}))
              filterableCols[item].selected = []
            }

            ElNotification({
              title: '温馨提示',
              message: '已成功加载' + data.data.length + '条数据',
              type: 'success',
              position: 'bottom-right'
            });
          })
          .catch(error => {
            console.error(error);
          });

    }
);
</script>