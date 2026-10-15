<template>
  <div style="height: 100vh">
    <t-enhanced-table
        :data="filterData"
        :columns="columns"
        row-key="index"
        hover
        :loading="loading"
        @filter-change="onFilterChange"
    />
  </div>
</template>

<style scoped>

</style>

<script setup>
import {computed, onMounted, ref} from "vue";
import {request} from "@/services";
import {API_ENDPOINTS as api} from "@/services/api";
import {NotifyPlugin} from "tdesign-vue-next";

const allData = ref([]);
const filterData = ref([]);
const loading = ref(false);

// 字典表名称筛选项(接口返回后填充)
const descFilters = ref([]);

// 表格列配置
const columns = computed(() => [
  {colKey: 'serial-number', title: '序号', width: 80},
  {
    colKey: 'desc',
    title: '字典表名称',
    width: 300,
    filter: {
      type: 'multiple',
      showConfirmAndReset: true,
      list: descFilters.value
    }
  },
  {colKey: 'value', title: '值', width: 100},
  {colKey: 'comment', title: '值含义', width: 300},
  {colKey: 'dict_name', title: '参考标准', width: 100},
]);

// 筛选变化时过滤数据
function onFilterChange(filters) {
  const selected = filters.desc || [];
  if (!selected.length) {
    filterData.value = allData.value;
    return;
  }
  filterData.value = allData.value.filter(item => selected.includes(item.desc));
}

onMounted(() => {
      loading.value = true;
      request(api.LIST_HIP_DICT, 'get')
          .then(response => {
            allData.value = response.data.map(item => (
                {index: item[0], dict_name: item[4], value: item[2], comment: item[3], desc: item[1]}
            ));
            filterData.value = allData.value;
            // 生成去重后的筛选项
            const map = new Map();
            response.data.forEach(el => map.set(el[1], {label: el[1], value: el[1]}));
            descFilters.value = [...map.values()];

            NotifyPlugin.success({
              title: '温馨提示',
              content: '已成功加载' + allData.value.length + '条数据',
              placement: 'bottom-right',
              duration: 3000
            });
          })
          .catch(error => {
            console.error(error);
          })
          .finally(() => {
            loading.value = false;
          });
    }
);
</script>
