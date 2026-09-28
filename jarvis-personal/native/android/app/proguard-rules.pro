# kotlinx.serialization keeps generated serializers.
-keepattributes *Annotation*, InnerClasses
-keepclassmembers class com.dincr.data.** { *** Companion; }
-keepclasseswithmembers class com.dincr.data.** { kotlinx.serialization.KSerializer serializer(...); }
