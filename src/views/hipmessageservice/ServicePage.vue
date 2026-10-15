<template>
  <t-table
      :data="data"
      :columns="columns"
      row-key="value"
      hover
      style="width: 100%"
      :loading="loading"
  />
</template>

<style scoped>

</style>

<script setup>
import {onMounted, ref} from "vue";
import {request} from "@/services";
import {API_ENDPOINTS as api} from "@/services/api";
import {NotifyPlugin} from "tdesign-vue-next";

const data = ref([]);
const loading = ref(false);

// 表格列配置
const columns = [
  {colKey: 'serial-number', title: '序号', width: 80},
  {colKey: 'dir', title: '类别'},
  {colKey: 'value', title: '服务代码'},
  {colKey: 'comment', title: '服务名称'},
  {colKey: 'remark', title: '等级'},
];

onMounted(() => {
      loading.value = true;
      request(api.LIST_HIP_SERVICE, 'get')
          .then(response => {
            data.value = response.data.map(item => ({"value": item[3], "comment": item[2], "dir": item[1], "remark": item[4]}));
            NotifyPlugin.success({
              title: '温馨提示',
              content: '已成功加载' + data.value.length + '条数据',
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
