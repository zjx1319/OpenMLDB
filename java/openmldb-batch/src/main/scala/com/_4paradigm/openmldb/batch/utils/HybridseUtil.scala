/*
 * Copyright 2021 4Paradigm
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com._4paradigm.openmldb.batch.utils

import java.util
import com._4paradigm.hybridse.`type`.TypeOuterClass.{ColumnDef, Database, TableDef, Type}
import com._4paradigm.hybridse.vm.{PhysicalLoadDataNode, PhysicalOpNode, PhysicalSelectIntoNode}
import com._4paradigm.hybridse.node.{ConstNode, DataType => InnerDataType}
import com._4paradigm.hybridse.sdk.UnsupportedHybridSeException
import org.apache.spark.sql.types.{
  BooleanType, DataType, DateType, DoubleType, FloatType, IntegerType, LongType,
  ShortType, StringType, StructField, StructType, TimestampType
}
import org.apache.spark.sql.{DataFrame, Row}
import scala.collection.JavaConverters.asScalaBufferConverter
import scala.collection.mutable


object HybridseUtil {
  def getOutputSchemaSlices(node: PhysicalOpNode, enableUnsafeRowOpt: Boolean): Array[StructType] = {
    if (enableUnsafeRowOpt) {
      // If enabling UnsafeRowOpt, return row with one slice
      val columnDefs = node.GetOutputSchema()
      Array(getSparkSchema(columnDefs))
    } else {
      (0 until node.GetOutputSchemaSourceSize().toInt).map(i => {
        val columnDefs = node.GetOutputSchemaSource(i).GetSchema()
        getSparkSchema(columnDefs)
      }).toArray
    }
  }

  def getDatabases(tableMap: mutable.Map[String, mutable.Map[String, DataFrame]]): List[Database] = {
    tableMap.map { case (dbName, tableDfMap) =>
      getDatabase(dbName, tableDfMap.toMap)
    }.toList
  }

  def getDatabase(databaseName: String, dict: Map[String, DataFrame]): Database = {
    val databaseBuilder = Database.newBuilder()
    databaseBuilder.setName(databaseName)
    dict.foreach { case (name, df) =>
      databaseBuilder.addTables(getTableDef(name, df))
    }
    databaseBuilder.build()
  }

  def getTableDef(tableName: String, dataFrame: DataFrame): TableDef = {
    val tblBulder = TableDef.newBuilder()
    dataFrame.schema.foreach(field => {
      tblBulder.addColumns(ColumnDef.newBuilder()
        .setName(field.name)
        .setIsNotNull(!field.nullable)
        .setType(DataTypeUtil.sparkTypeToHybridseProtoType(field.dataType))
        .build()
      )
    })
    tblBulder.setName(tableName)
    tblBulder.build()
  }

  def getHybridseSchema(structType: StructType): java.util.List[ColumnDef] = {
    val list = new util.ArrayList[ColumnDef]()
    structType.foreach(field => {
      list.add(ColumnDef.newBuilder()
        .setName(field.name)
        .setIsNotNull(!field.nullable)
        .setType(DataTypeUtil.sparkTypeToHybridseProtoType(field.dataType)).build())
    })
    list
  }

  def getSparkSchema(columns: java.util.List[ColumnDef]): StructType = {
    StructType(columns.asScala.map(col => {
      StructField(col.getName, DataTypeUtil.hybridseProtoTypeToSparkType(col.getType), !col.getIsNotNull)
    }))
  }

  def createGroupKeyComparator(keyIdxs: Array[Int]): (Row, Row) => Boolean = {
    if (keyIdxs.length == 1) {
      val idx = keyIdxs(0)
      (row1, row2) => {
        row1.get(idx) != row2.get(idx)
      }
    } else {
      (row1, row2) => {
        keyIdxs.exists(i => row1.get(i) != row2.get(i))
      }
    }
  }

  def parseOption(node: ConstNode, default: String, f: (ConstNode, String) => String): String = {
    f(node, default)
  }

  def getBoolOrDefault(node: ConstNode, default: String): String = {
    if (node != null) {
      node.GetBool().toString
    } else {
      default
    }
  }

  def updateOptionsMap(options: mutable.Map[String, String], node: ConstNode, name: String, getValue: ConstNode =>
    String): Unit = {
    if (node != null) {
      options += (name -> getValue(node))
    }
  }

  def getStringOrDefault(node: ConstNode, default: String): String = {
    if (node != null) {
      node.GetStr()
    } else {
      default
    }
  }

  def getBool(node: ConstNode): String = {
    node.GetBool().toString
  }

  def getStr(node: ConstNode): String = {
    node.GetStr()
  }

  def getOptionFromNode[T](node: T, name: String): ConstNode = {
    node match {
      case node1: PhysicalSelectIntoNode => node1.GetOption(name)
      case node1: PhysicalLoadDataNode => node1.GetOption(name)
      case _ => throw new UnsupportedHybridSeException(s"${node.getClass} doesn't support GetOption method")
    }
  }

  def parseOptions[T](node: T): (String, Map[String, String], String, Option[Boolean]) = {
    // load data: read format, select into: write format
    val format = parseOption(getOptionFromNode(node, "format"), "csv", getStringOrDefault).toLowerCase
    require(format.equals("csv") || format.equals("parquet"))

    // load data: read options, select into: write options
    val options: mutable.Map[String, String] = mutable.Map()
    // default values:
    // delimiter -> sep: ,
    // header: true(different with spark)
    // null_value -> nullValue: null(different with spark)
    // quote: '\0'(means no quote, the same with spark quote "empty string")
    options += ("header" -> "true")
    options += ("nullValue" -> "null")
    updateOptionsMap(options, getOptionFromNode(node, "delimiter"), "sep", getStr)
    updateOptionsMap(options, getOptionFromNode(node, "header"), "header", getBool)
    updateOptionsMap(options, getOptionFromNode(node, "null_value"), "nullValue", getStr)
    updateOptionsMap(options, getOptionFromNode(node, "quote"), "quote", getStr)

    // load data: write mode(load data may write to offline storage or online storage, needs mode too)
    // select into: write mode
    val modeStr = parseOption(getOptionFromNode(node, "mode"), "error_if_exists", HybridseUtil
      .getStringOrDefault).toLowerCase
    val mode = modeStr match {
      case "error_if_exists" => "errorifexists"
      // append/overwrite, stay the same
      case "append" | "overwrite" => modeStr
      case others: Any => throw new UnsupportedHybridSeException(s"unsupported write mode $others")
    }

    // only for PhysicalLoadDataNode
    var deepCopy: Option[Boolean] = None
    if (node.isInstanceOf[PhysicalLoadDataNode]) {
      deepCopy = Option(parseOption(getOptionFromNode(node, "deep_copy"), "true", getBoolOrDefault).toBoolean)
    }
    (format, options.toMap, mode, deepCopy)
  }
}
