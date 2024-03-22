import { defineStore } from 'pinia';

// 第一个参数是应用程序中 store 的唯一 id
const messageStore= defineStore({
  id: 'message',
  state: () => {
    return {
      message: "hello word"
    }
  },
  actions: {
    set_message(message) {
      this.message = message;
    }
  }
});

export {messageStore}