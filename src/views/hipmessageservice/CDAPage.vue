<template>
  <el-table :data="data" style="width: 100%" highlight-current-row>
    <el-table-column type="index" label="序号" width="80"/>
    <el-table-column prop="value" label="服务代码"/>
    <el-table-column prop="comment" label="服务名称" />
    <el-table-column prop="remark" label="等级" />
  </el-table>
</template>

<style scoped>

</style>

<script setup>
import {onMounted, ref} from "vue";
import service from "@/services";
import {API_ENDPOINTS as api} from "@/services/api";
import {ElNotification, ElTable, ElTableColumn} from "element-plus";

const data = ref([]);

onMounted(() => {
      service.get(api.LIST_HIP_CDA)
          .then(response => {
            data.value = response.data.map(item => ({"value": item[1], "comment": item[2], "remark": item[3]}));
            ElNotification({
              title: '温馨提示',
              message: '已成功加载' + data.value.length + '条数据',
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
