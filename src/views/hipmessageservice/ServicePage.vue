<template>
  <el-table :data="data" style="width: 100%" highlight-current-row height="10v0h">
    <el-table-column type="index" label="序号" width="80"/>
    <el-table-column prop="dir" label="类别" />
    <el-table-column prop="value" label="服务代码"/>
    <el-table-column prop="comment" label="服务名称" />
    <el-table-column prop="remark" label="等级" />
  </el-table>
</template>

<style scoped>

</style>

<script setup>
import {onMounted, ref} from "vue";
import {request} from "@/services";
import {API_ENDPOINTS as api} from "@/services/api";
import {ElNotification, ElTable, ElTableColumn} from "element-plus";

const data = ref([]);

onMounted(() => {
      request(api.LIST_HIP_SERVICE, 'get')
          .then(response => {
            data.value = response.data.map(item => ({"value": item[3], "comment": item[2], "dir": item[1], "remark": item[4]}));
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